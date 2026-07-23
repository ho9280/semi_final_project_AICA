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
from datetime import date, datetime, timedelta
from pathlib import Path

from app.menu.config import (
    DEFAULT_MEAL_TYPE,
    DEFAULT_ORGANIZATION_CODES,
    DINNER_ORGANIZATION_CODES,
    KST,
    MEAL_TYPE_SYNONYMS,
    ORGANIZATIONS,
    WEEKDAYS,
)
from app.menu.menu_embedding import VectorStore
from app.menu.menu_ocr import MockOCRProvider, OCRProvider
from app.menu.menu_parser import parse_ocr_text
from app.menu.menu_repository import MenuRepository

_WEEKDAY_PATTERN = re.compile(r"[월화수목금토일]요일")
_DATE_PATTERN = re.compile(r"(\d{4})[-./년]\s*(\d{1,2})[-./월]\s*(\d{1,2})일?")

# "이번 주에 돈가스 나오는 날이 언제야?" 처럼 특정 메뉴가 나오는 날짜 자체를 묻는
# 질문인지 판단하는 키워드. 이런 질문은 조건 검색이 아니라 의미 검색으로 처리한다.
_SEMANTIC_INTENT_KEYWORDS = ["언제", "나오는", "나온다", "나와"]

# 사용자가 끼니를 직접 말하지 않았을 때 현재 시각으로 끼니/날짜 기본값을 정하는 기준.
_LUNCH_WINDOW_START_HOUR = 0
_DINNER_WINDOW_START_HOUR = 13
_NEXT_DAY_WINDOW_START_HOUR = 19


def get_now_kst() -> datetime:
    """한국 시간(KST) 기준 현재 시각을 반환한다."""
    return datetime.now(KST)


def get_today_kst() -> date:
    """한국 시간(KST) 기준 오늘 날짜를 반환한다."""
    return get_now_kst().date()


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
    """질문에서 끼니를 추출하고 표준값("점심"/"저녁"/"아침")으로 변환한다.

    "중식"/"런치" -> "점심", "석식"/"디너" -> "저녁" 처럼 다양한 표현을
    표준값 하나로 정규화하므로, 이후 SQLite 조회는 항상 표준값으로 이뤄진다.
    """
    for word, standard in MEAL_TYPE_SYNONYMS.items():
        if word in text:
            return standard
    return None


def _is_semantic_intent(text: str) -> bool:
    """"돈가스 나오는 날이 언제야?"처럼 날짜 자체를 찾는 질문인지 판단한다."""
    return any(keyword in text for keyword in _SEMANTIC_INTENT_KEYWORDS)


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


def _resolve_meal_type(filters: QueryFilters, now: datetime) -> str:
    """사용자가 끼니를 지정하지 않았을 때 현재 시각으로 기본 끼니를 정한다.

    00시~13시: 점심 / 13시~19시: 저녁(대성학원) / 19시 이후: 다음 식단 제공일 점심.
    사용자가 끼니를 직접 말한 경우에는 이 시간대 기본값보다 사용자 요청이 우선한다.
    """
    if filters.meal_type is not None:
        return filters.meal_type

    hour = now.hour
    if _LUNCH_WINDOW_START_HOUR <= hour < _DINNER_WINDOW_START_HOUR:
        return DEFAULT_MEAL_TYPE
    if _DINNER_WINDOW_START_HOUR <= hour < _NEXT_DAY_WINDOW_START_HOUR:
        return "저녁"
    return DEFAULT_MEAL_TYPE


def _resolve_menu_date(filters: QueryFilters, now: datetime, today: date) -> str | None:
    """조건 검색에 사용할 날짜를 정한다.

    사용자가 날짜(오늘/내일/특정 날짜)나 요일을 직접 언급했으면 그대로 쓰고,
    요일만 언급한 경우에는 요일 조건만으로 조회하도록 날짜를 비워둔다(None).
    둘 다 없을 때만 시간대 기본값을 적용한다: 19시 이후 + 끼니 미지정이면
    다음 식단 제공일(내일)의 점심을, 그 외에는 오늘 날짜를 사용한다.
    """
    if filters.menu_date:
        return filters.menu_date
    if filters.weekday:
        return None

    if filters.meal_type is None and now.hour >= _NEXT_DAY_WINDOW_START_HOUR:
        return (today + timedelta(days=1)).isoformat()
    return today.isoformat()


def _resolve_organization_codes(filters: QueryFilters, meal_type: str) -> list[str]:
    """조회 대상 업체 코드를 정한다.

    사용자가 업체를 지정하면 그 업체만, 지정하지 않았고 끼니가 저녁이면
    저녁을 제공하는 업체(대성학원)만, 그 외에는 기본 업체 조합(대성학원+KT)을 쓴다.
    KT/KT 샐러드는 저녁 데이터가 없으므로 임의로 포함하지 않는다.
    """
    if filters.organization_code is not None:
        return [filters.organization_code]
    if meal_type == "저녁":
        return DINNER_ORGANIZATION_CODES
    return DEFAULT_ORGANIZATION_CODES


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
    now: datetime | None = None,
) -> dict:
    """사용자의 메뉴 질문을 처리하고 통일된 결과를 반환한다.

    now: 시간대 기본값(점심/저녁, 다음 식단 제공일) 계산에 쓰는 기준 시각.
    테스트에서 특정 시각을 고정하고 싶을 때 전달한다. 생략하면 한국 시간
    기준 현재 시각을 사용한다.

    반환값은 항상 다음 형태를 유지한다 (예외가 발생해도 동일).
    {"success": bool, "query": str, "results": list[dict], "answer": str}
    """
    repository = repository or MenuRepository()
    vector_store = vector_store or VectorStore()
    now = now or get_now_kst()
    today = today or now.date()

    try:
        filters = parse_query(query, today=today)

        if not filters.menu_date and not filters.weekday and _is_semantic_intent(query):
            # "돈가스 나오는 날이 언제야?" 처럼 날짜 자체를 찾는 질문은 의미 검색으로 처리한다.
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
        else:
            # 업체/날짜(또는 요일)를 조건 검색으로 조회한다.
            # 사용자가 끼니를 지정하지 않았다면 현재 시각으로 기본값을 정하고,
            # 해당 조건에 데이터가 없어도 다른 날짜/끼니로 대체하지 않는다.
            meal_type = _resolve_meal_type(filters, now)
            menu_date = _resolve_menu_date(filters, now, today)
            org_codes = _resolve_organization_codes(filters, meal_type)
            org_display_list = [ORGANIZATIONS[code]["display_name"] for code in org_codes]

            raw_results = []
            for org_display in org_display_list:
                raw_results.extend(
                    repository.get_by_condition(
                        organization=org_display,
                        menu_date=menu_date,
                        weekday=filters.weekday,
                        meal_type=meal_type,
                    )
                )
            search_mode = "condition"

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
