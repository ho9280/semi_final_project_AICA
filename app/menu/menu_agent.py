"""메뉴 질문 처리의 전체 흐름을 연결하는 모듈.

질문 분석 -> (조건 검색 또는 의미 검색) -> 결과 정리 -> 답변 텍스트 생성까지
한 번에 처리하는 ``query_menu()``가 이 모듈의 핵심이다. 다른 Agent나
FastAPI 라우터, LangGraph Router가 호출할 진입점으로 설계했다.

또한 관리자가 새 식단표 이미지를 등록할 때 쓰는 ``register_menu_image()``도
제공한다 (OCR -> 구조화 -> SQLite 저장 -> 임베딩 저장까지 한 번에 처리).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from app.menu.config import (
    DEFAULT_MEAL_TYPE,
    DEFAULT_ORGANIZATION_CODES,
    KST,
    MEAL_TYPES,
    ORGANIZATIONS,
    WEEKDAYS,
)
from app.menu.menu_embedding import VectorStore
from app.menu.menu_ocr import MockOCRProvider, OCRProvider
from app.menu.menu_parser import parse_ocr_text
from app.menu.menu_repository import MenuRepository

_WEEKDAY_PATTERN = re.compile(r"[월화수목금토일]요일")
_DATE_PATTERN = re.compile(r"(\d{4})[-./년]\s*(\d{1,2})[-./월]\s*(\d{1,2})일?")


def get_today_kst() -> date:
    """한국 시간(KST) 기준 오늘 날짜를 반환한다."""
    from datetime import datetime

    return datetime.now(KST).date()


@dataclass
class QueryFilters:
    organization_code: str | None = None
    organization_display: str | None = None
    menu_date: str | None = None
    weekday: str | None = None
    meal_type: str | None = None


def _extract_organization(text: str) -> tuple[str | None, str | None]:
    lowered = text.lower()
    # dict 순서대로 검사한다. config.py에서 "kt_salad"가 "kt"보다 먼저
    # 오도록 정의해두었기 때문에 "KT 샐러드"가 "KT"보다 먼저 매칭된다.
    for code, info in ORGANIZATIONS.items():
        for alias in info["aliases"]:
            if alias.lower() in lowered:
                return code, info["display_name"]
    return None, None


def _extract_date(text: str, today: date) -> str | None:
    if "오늘" in text:
        return today.isoformat()
    if "내일" in text:
        return (today + timedelta(days=1)).isoformat()
    if "모레" in text:
        return (today + timedelta(days=2)).isoformat()

    match = _DATE_PATTERN.search(text)
    if match:
        year, month, day = (int(g) for g in match.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None

    return None


def _extract_weekday(text: str) -> str | None:
    match = _WEEKDAY_PATTERN.search(text)
    if match and match.group(0) in WEEKDAYS:
        return match.group(0)
    return None


def _extract_meal_type(text: str) -> str | None:
    for meal_type in MEAL_TYPES:
        if meal_type in text:
            return meal_type
    return None


def parse_query(query: str, today: date | None = None) -> QueryFilters:
    """사용자 질문에서 업체/날짜/요일/식사종류를 추출한다.

    MVP에서는 복잡한 LLM 호출 대신 키워드 매칭과 간단한 날짜 계산만 사용한다.
    """
    today = today or get_today_kst()
    org_code, org_display = _extract_organization(query)

    return QueryFilters(
        organization_code=org_code,
        organization_display=org_display,
        menu_date=_extract_date(query, today),
        weekday=_extract_weekday(query),
        meal_type=_extract_meal_type(query),
    )


def _strip_internal_fields(entry: dict) -> dict:
    return {
        "organization": entry["organization"],
        "menu_type": entry["menu_type"],
        "menu_date": entry["menu_date"],
        "weekday": entry["weekday"],
        "meal_type": entry["meal_type"],
        "menu_items": entry["menu_items"],
        "source_image_path": entry["source_image_path"],
    }


def _date_phrase(filters: QueryFilters, today: date) -> str:
    if filters.menu_date:
        if filters.menu_date == today.isoformat():
            return "오늘"
        if filters.menu_date == (today + timedelta(days=1)).isoformat():
            return "내일"
        return filters.menu_date
    if filters.weekday:
        return filters.weekday
    return "요청하신"


def _build_answer(
    filters: QueryFilters, results: list[dict], today: date, search_mode: str
) -> str:
    if not results:
        if search_mode == "condition":
            # 날짜(또는 요일) 조건으로 조회했는데 결과가 없는 경우.
            # 다른 날짜의 메뉴로 대체하지 않고, 정해진 안내 문구만 반환한다.
            return "해당 날짜에는 등록된 식단이 없습니다."
        org_phrase = f" {filters.organization_display}" if filters.organization_display else ""
        return f"{_date_phrase(filters, today)}{org_phrase} 식단 정보가 등록되어 있지 않습니다."

    if len(results) == 1:
        r = results[0]
        items = ", ".join(r["menu_items"])
        date_phrase = _date_phrase(filters, today)
        if date_phrase == "요청하신":
            date_phrase = r["menu_date"]
        return f"{date_phrase} {r['organization']} {r['meal_type']} 메뉴는 {items}입니다."

    lines = [
        f"[{r['menu_date']} {r['weekday']}] {r['organization']} {r['meal_type']}: {', '.join(r['menu_items'])}"
        for r in results
    ]
    return "\n".join(lines)


def query_menu(
    query: str,
    repository: MenuRepository | None = None,
    vector_store: VectorStore | None = None,
    today: date | None = None,
) -> dict:
    """사용자의 메뉴 질문을 처리하고 통일된 결과를 반환한다.

    반환값은 항상 다음 형태를 유지한다 (예외가 발생해도 동일).
    {"success": bool, "query": str, "results": list[dict], "answer": str}
    """
    repository = repository or MenuRepository()
    vector_store = vector_store or VectorStore()
    today = today or get_today_kst()

    try:
        filters = parse_query(query, today=today)

        # 끼니를 지정하지 않으면 중식(점심)을 기본값으로 사용한다.
        meal_type = filters.meal_type or DEFAULT_MEAL_TYPE

        if filters.organization_code is not None:
            # 사용자가 업체를 명시한 경우 (예: "샐러드", "KT 샐러드"도 여기서 처리되어
            # KT 샐러드가 조회 대상에 포함된다).
            org_display_list = [filters.organization_display]
        else:
            # 업체 미지정 시 기본값은 대성학원 + KT이며, KT 샐러드는 제외한다.
            org_display_list = [
                ORGANIZATIONS[code]["display_name"] for code in DEFAULT_ORGANIZATION_CODES
            ]

        if filters.menu_date or filters.weekday:
            # 업체/날짜(또는 요일)가 명확하므로 조건 검색을 우선 사용한다.
            # 해당 조건에 데이터가 없어도 다른 날짜로 대체하지 않는다.
            raw_results = []
            for org_display in org_display_list:
                raw_results.extend(
                    repository.get_by_condition(
                        organization=org_display,
                        menu_date=filters.menu_date,
                        weekday=filters.weekday,
                        meal_type=meal_type,
                    )
                )
            search_mode = "condition"
        else:
            # 명확한 날짜/요일이 없으므로 의미 검색으로 보조한다.
            metadata_filter = (
                {"organization": filters.organization_display}
                if filters.organization_code is not None
                else None
            )
            hits = vector_store.search(query, top_k=5, metadata_filter=metadata_filter)
            raw_results = []
            for hit in hits:
                if hit["score"] <= 0:
                    continue
                entry = repository.get_by_id(hit["id"])
                if not entry:
                    continue
                # 업체 미지정 기본 결과에서는 KT 샐러드를 제외한다.
                if (
                    filters.organization_code is None
                    and entry["organization"] == ORGANIZATIONS["kt_salad"]["display_name"]
                ):
                    continue
                raw_results.append(entry)
            search_mode = "semantic"

        results = [_strip_internal_fields(r) for r in raw_results]
        answer = _build_answer(filters, results, today, search_mode)

        return {
            "success": len(results) > 0,
            "query": query,
            "results": results,
            "answer": answer,
        }
    except Exception as exc:  # 어떤 예외가 나도 동일한 구조를 유지한다.
        return {
            "success": False,
            "query": query,
            "results": [],
            "answer": f"메뉴 조회 중 오류가 발생했습니다: {exc}",
        }


def register_menu_image(
    image_path: str | Path,
    organization_code: str,
    ocr_provider: OCRProvider | None = None,
    repository: MenuRepository | None = None,
    vector_store: VectorStore | None = None,
) -> dict:
    """식단표 이미지 한 장을 OCR -> 구조화 -> 저장까지 처리한다.

    성공하면 {"success": True, "registered_ids": [...], "error": None}을,
    실패하면 {"success": False, "registered_ids": [], "error": "사유"}를 반환한다.
    """
    org_info = ORGANIZATIONS.get(organization_code)
    if org_info is None:
        return {
            "success": False,
            "registered_ids": [],
            "error": f"알 수 없는 업체 코드입니다: {organization_code}",
        }

    ocr_provider = ocr_provider or MockOCRProvider()
    repository = repository or MenuRepository()
    vector_store = vector_store or VectorStore()

    ocr_result = ocr_provider.extract_text(image_path)
    if not ocr_result.success:
        return {"success": False, "registered_ids": [], "error": ocr_result.error}

    parse_result = parse_ocr_text(
        ocr_result.text,
        organization=org_info["display_name"],
        menu_type=org_info["menu_type"],
        source_image_path=str(image_path),
    )
    if not parse_result.success:
        return {"success": False, "registered_ids": [], "error": parse_result.error}

    registered_ids = []
    for entry in parse_result.entries:
        entry_id = repository.upsert_menu_entry(entry)
        embedding_text = (
            f"{entry['organization']} {entry['menu_type']} {entry['menu_date']} "
            f"{entry['weekday']} {entry['meal_type']}: {', '.join(entry['menu_items'])}"
        )
        vector_store.upsert(
            entry_id,
            embedding_text,
            metadata={
                "organization": entry["organization"],
                "menu_date": entry["menu_date"],
                "weekday": entry["weekday"],
                "meal_type": entry["meal_type"],
                "source_image_path": entry["source_image_path"],
            },
        )
        registered_ids.append(entry_id)

    return {"success": True, "registered_ids": registered_ids, "error": None}


if __name__ == "__main__":
    # 간단한 수동 확인용 진입점: uv run python -m app.menu.menu_agent
    result = query_menu("오늘 KT 메뉴 뭐야?")
    print(result["answer"])
