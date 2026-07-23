"""data/menu 폴더의 이미지 + 같은 이름의 .txt(sidecar)를 원본 데이터로 쓰는
파일 기반 메뉴 저장소.

최종 정의서 기준으로 메뉴 데이터는 별도의 관계형 DB 테이블로 관리하지 않는다.
`app/menu/menu_repository.py`(SQLite)는 삭제하지 않고 호환용으로 남겨두지만,
`get_menu()`/`get_current_menu()`의 기본 실행 경로는 이 모듈만 사용하며
`menu.db`를 만들지 않는다.

동작 방식:
    data/menu/{daesung,kt,kt_salad}/*.{png,jpg,jpeg}
    각 이미지와 같은 이름의 .txt 파일을 OCR 결과처럼 읽어(MockOCRProvider)
    menu_parser로 구조화한 뒤 메모리에 올려둔다.

새 식단표 이미지를 추가한 뒤에는 코드를 고치지 않고 ``reload_menu_data()``만
다시 호출하면 된다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.menu.config import BASE_DIR, ORGANIZATIONS, SUPPORTED_IMAGE_EXTENSIONS
from app.menu.menu_embedding import VectorStore, get_vector_store
from app.menu.menu_ocr import MockOCRProvider, OCRProvider
from app.menu.menu_parser import parse_ocr_text
from app.menu.menu_repository import make_entry_id


@dataclass
class LoadError:
    image_path: str
    error: str


@dataclass
class LoadResult:
    entry_count: int
    errors: list[LoadError] = field(default_factory=list)


def _to_display_path(image_path: Path) -> str:
    """가능하면 프로젝트 루트 기준 상대 경로로 저장한다 (컴퓨터마다 다른
    절대 경로를 데이터/결과에 고정하지 않기 위함).
    """
    try:
        return str(image_path.relative_to(BASE_DIR))
    except ValueError:
        return str(image_path)


class MenuFileStore:
    """업체 폴더를 스캔해 메모리에 올려두는 저장소. 인스턴스마다 독립적이다."""

    def __init__(
        self,
        data_dir: str | Path | None = None,
        ocr_provider: OCRProvider | None = None,
    ) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else None
        self.ocr_provider = ocr_provider or MockOCRProvider()
        self._entries: dict[str, dict] = {}
        self._errors: list[LoadError] = []

    def _organization_folder(self, org_code: str) -> Path:
        if self.data_dir is not None:
            return self.data_dir / org_code
        return ORGANIZATIONS[org_code]["dir"]

    def load(self, vector_store: VectorStore | None = None) -> LoadResult:
        """모든 업체 폴더를 다시 스캔해 메모리 데이터를 새로 만든다.

        기존 데이터는 이번에 스캔한 결과로 완전히 교체된다(재조회 시 지워진
        이미지의 옛 데이터가 남지 않는다). 같은 (업체, 메뉴종류, 날짜, 식사종류)
        조합은 같은 id로 계산되므로 나중에 읽은 값이 앞의 값을 덮어써
        중복이 쌓이지 않는다.

        이미지가 없거나(OCR 실패), 형식에 맞지 않는(.txt 파싱 실패) 파일이
        있어도 전체 스캔을 중단하지 않고 errors 목록에 모아 반환한다.
        """
        entries: dict[str, dict] = {}
        errors: list[LoadError] = []

        for org_code, org_info in ORGANIZATIONS.items():
            folder = self._organization_folder(org_code)
            if not folder.exists():
                continue

            for image_path in sorted(folder.iterdir()):
                if not image_path.is_file():
                    continue
                if image_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
                    continue  # .txt, .db 등 이미지가 아닌 파일은 조용히 건너뛴다

                try:
                    ocr_result = self.ocr_provider.extract_text(image_path)
                    if not ocr_result.success:
                        errors.append(LoadError(str(image_path), ocr_result.error))
                        continue

                    parse_result = parse_ocr_text(
                        ocr_result.text,
                        organization=org_info["display_name"],
                        menu_type=org_info["menu_type"],
                        source_image_path=_to_display_path(image_path),
                    )
                    if not parse_result.success:
                        errors.append(LoadError(str(image_path), parse_result.error))
                        continue

                    for entry in parse_result.entries:
                        entry_id = make_entry_id(
                            entry["organization"],
                            entry["menu_type"],
                            entry["menu_date"],
                            entry["meal_type"],
                        )
                        entries[entry_id] = entry
                except Exception as exc:  # 파일 하나가 잘못돼도 전체 실행은 계속한다.
                    errors.append(LoadError(str(image_path), f"처리 중 오류: {exc}"))

        self._entries = entries
        self._errors = errors

        if vector_store is not None:
            for entry_id, entry in entries.items():
                text = (
                    f"{entry['organization']} {entry['menu_type']} {entry['menu_date']} "
                    f"{entry['weekday']} {entry['meal_type']}: {', '.join(entry['menu_items'])}"
                )
                vector_store.upsert(
                    entry_id,
                    text,
                    metadata={
                        "organization": entry["organization"],
                        "menu_date": entry["menu_date"],
                        "weekday": entry["weekday"],
                        "meal_type": entry["meal_type"],
                        "source_image_path": entry["source_image_path"],
                    },
                )

        return LoadResult(entry_count=len(entries), errors=errors)

    @property
    def errors(self) -> list[LoadError]:
        return list(self._errors)

    def get_by_id(self, entry_id: str) -> dict | None:
        return self._entries.get(entry_id)

    def get_by_condition(
        self,
        organization: str | None = None,
        menu_date: str | None = None,
        weekday: str | None = None,
        meal_type: str | None = None,
    ) -> list[dict]:
        results = []
        for entry in self._entries.values():
            if organization is not None and entry["organization"] != organization:
                continue
            if menu_date is not None and entry["menu_date"] != menu_date:
                continue
            if weekday is not None and entry["weekday"] != weekday:
                continue
            if meal_type is not None and entry["meal_type"] != meal_type:
                continue
            results.append(entry)
        results.sort(key=lambda e: (e["menu_date"], e["organization"], e["meal_type"]))
        return results

    def get_all(self) -> list[dict]:
        return sorted(
            self._entries.values(), key=lambda e: (e["menu_date"], e["organization"], e["meal_type"])
        )

    def count(self) -> int:
        return len(self._entries)


_default_store: MenuFileStore | None = None


def get_store() -> MenuFileStore:
    """기본(data/menu 전체) MenuFileStore 싱글턴을 반환한다. 처음 호출될 때만 스캔한다."""
    global _default_store
    if _default_store is None:
        _default_store = MenuFileStore()
        _default_store.load(vector_store=get_vector_store())
    return _default_store


def reload_menu_data(ocr_provider: OCRProvider | None = None) -> dict:
    """data/menu 폴더를 다시 스캔해 최신 이미지/텍스트를 반영한다.

    새 식단표 이미지(.png/.jpg/.jpeg)와 같은 이름의 .txt를 폴더에 추가한 뒤
    이 함수를 호출하면, 코드를 다시 고치지 않아도 바로 조회할 수 있다.

    반환값:
        {
            "entry_count": int,          # 새로 인식된 식단 항목 수
            "errors": [                  # 처리하지 못한 파일 목록(전체 실행은 중단하지 않음)
                {"image_path": str, "error": str}, ...
            ],
        }
    """
    global _default_store
    _default_store = MenuFileStore(ocr_provider=ocr_provider) if ocr_provider else MenuFileStore()
    result = _default_store.load(vector_store=get_vector_store())
    return {
        "entry_count": result.entry_count,
        "errors": [{"image_path": e.image_path, "error": e.error} for e in result.errors],
    }
