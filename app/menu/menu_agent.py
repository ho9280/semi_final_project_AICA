"""메뉴 질문(챗봇) 처리의 전체 흐름을 연결하는 모듈.

질문 분석 -> (조건 검색 또는 의미 검색) -> 결과 정리 -> 답변 텍스트 생성까지
한 번에 처리하는 ``query_menu()``가 이 모듈의 핵심이다. 최종 정의서 기준으로
챗봇 질문(이 모듈)과 대시보드 시간 자동 표시(``menu_tool.get_current_menu()``)는
서로 다른 기본값 규칙을 쓰므로 분리되어 있다: 챗봇은 끼니를 지정하지 않으면
현재 시각과 무관하게 항상 "점심"을 기본값으로 쓴다.

기본 데이터 원본은 SQLite가 아니라 ``menu_file_store.py``가 관리하는
``data/menu/`` 폴더의 이미지 + .txt(sidecar)이다. ``menu_repository.py``(SQLite)는
삭제하지 않고 호환용으로 남아 있지만 ``query_menu()``의 기본 실행 경로에서는
쓰지 않는다 (``register_menu_image()``만 SQLite 등록용으로 계속 제공한다).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from app.menu.config import (
    DEFAULT_MEAL_TYPE,
    DEFAULT_ORGANIZATION_CODES,
    KST,
    MEAL_TYPE_SYNONYMS,
    ORGANIZATIONS,
    WEEKDAYS,
)
from app.menu.menu_embedding import VectorStore, get_vector_store
from app.menu.menu_file_store import MenuFileStore, get_store
from app.menu.menu_ocr import MockOCRProvider, OCRProvider
from app.menu.menu_parser import parse_ocr_text
from app.menu.menu_repository import MenuRepository

_WEEKDAY_PATTERN = re.compile(r"[월화수목금토일]요일")
_DATE_PATTERN = re.compile(r"(\d{4})[-./년]\s*(\d{1,2})[-./월]\s*(\d{1,2})일?")

# 하이브리드 검색용 키워드를 뽑아낼 때, 업체/날짜/요일/끼니를 제거하고 남은
# 토큰 중 이런 일반적인 질문 표현은 "메뉴 이름/재료"가 아니므로 제외한다.
_SEARCH_STOPWORDS = {
    "메뉴",
    "알려줘",
    "알려주세요",
    "줘",
    "주세요",
    "뭐야",
    "뭐지",
    "뭐예요",
    "궁금해",
    "있어",
    "있나요",
    "좀",
    "이번",
    "주에",
    "이번주",
    "언제",
    "나오는",
    "나온다",
    "나와",
    "날",
    "날짜",
    "혹시",
    "그",
}


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


def _extract_search_keyword(query: str, filters: QueryFilters) -> str:
    """질문에서 업체/날짜/요일/끼니/일반 질문 표현을 제거하고 남는 "메뉴 이름이나
    재료 이름으로 보이는" 핵심 검색어를 뽑아낸다.

    예) "KT 샐러드 방울토마토 메뉴" -> "방울토마토"
        "이번 주에 돈가스 나오는 날이 언제야?" -> "돈가스"
        "KT 메뉴 알려줘" -> "" (남는 키워드가 없으면 하이브리드 검색을 쓰지 않는다)
    """
    text = query

    if filters.organization_code is not None:
        alias_list = ORGANIZATIONS[filters.organization_code]["aliases"]
        lowered = text.lower()
        # 가장 긴 별칭부터 검사해야 "kt 샐러드"가 "kt"보다 먼저 제거된다.
        for alias in sorted(alias_list, key=len, reverse=True):
            idx = lowered.find(alias.lower())
            if idx != -1:
                text = text[:idx] + text[idx + len(alias) :]
                break

    for word in ("오늘", "내일", "모레"):
        text = text.replace(word, "")

    if filters.weekday:
        text = text.replace(filters.weekday, "")

    for word in MEAL_TYPE_SYNONYMS:
        text = text.replace(word, "")

    tokens = [t.strip("?!.,~ ") for t in re.split(r"\s+", text)]
    tokens = [t for t in tokens if t and t not in _SEARCH_STOPWORDS]
    return " ".join(tokens).strip()


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


def _resolve_meal_type(filters: QueryFilters) -> str:
    """끼니를 지정하지 않으면 현재 시각과 무관하게 항상 중식(점심)을 기본값으로 쓴다.

    시간대별 기본값(00~13시 점심 / 13~19시 저녁 / 19시 이후 다음날 점심)은
    챗봇이 아니라 대시보드(``menu_tool.get_current_menu()``)에서만 적용된다.
    사용자가 끼니를 직접 말한 경우에는 그 값을 그대로 쓴다.
    """
    return filters.meal_type or DEFAULT_MEAL_TYPE


def _resolve_menu_date(filters: QueryFilters, today: date) -> str | None:
    """조건 검색에 사용할 날짜를 정한다.

    사용자가 날짜(오늘/내일/특정 날짜)를 직접 언급했으면 그대로 쓰고,
    요일만 언급한 경우에는 요일 조건만으로 조회하도록 날짜를 비워둔다(None).
    둘 다 없으면 항상 오늘 날짜를 사용한다.
    """
    if filters.menu_date:
        return filters.menu_date
    if filters.weekday:
        return None
    return today.isoformat()


def _resolve_organization_codes(filters: QueryFilters) -> list[str]:
    """조회 대상 업체 코드를 정한다.

    사용자가 업체를 지정하면 그 업체만, 지정하지 않으면 기본 업체 조합
    (대성학원 + KT + KT 샐러드) 전체를 조회한다. KT/KT 샐러드에 저녁 데이터가
    없으면(끼니가 저녁인 경우) 해당 업체는 결과가 없을 뿐, 대신 다른 메뉴를
    임의로 채우지 않는다.
    """
    if filters.organization_code is not None:
        return [filters.organization_code]
    return DEFAULT_ORGANIZATION_CODES


def plan_menu_search(query: str, filters: QueryFilters, today: date) -> dict:
    """이 질문을 조건 검색으로 처리할지 하이브리드(메뉴명/재료) 검색으로 처리할지,
    어떤 조건으로 검색할지 결정한다. ``query_menu()``와 공개 Menu Tool
    (``menu_tool.py``)이 똑같은 판단 로직을 공유하도록 이 함수 하나로 모아둔다
    (로직 중복 방지).

    반환값:
        {
            "search_mode": "condition" | "hybrid",
            "organization_codes": list[str] | None,  # hybrid에서 None이면 전체 업체 대상
            "menu_date": str | None,
            "weekday": str | None,
            "meal_type": str | None,
            "keyword": str | None,  # "hybrid"일 때만 의미 있음
        }
    """
    if filters.menu_date or filters.weekday:
        # 업체/날짜(또는 요일)가 명확하므로 조건 검색을 그대로 쓴다(기존 동작 유지).
        meal_type = _resolve_meal_type(filters)
        org_codes = _resolve_organization_codes(filters)
        return {
            "search_mode": "condition",
            "organization_codes": org_codes,
            "menu_date": filters.menu_date,
            "weekday": filters.weekday,
            "meal_type": meal_type,
            "keyword": None,
        }

    keyword = _extract_search_keyword(query, filters)
    if keyword:
        # "방울토마토", "오렌지치킨텐더샐러드", "KT 참깨흑임자드레싱 나오는 날"처럼
        # 메뉴 이름/재료로 보이는 검색어가 남으면 하이브리드 검색을 쓴다.
        return {
            "search_mode": "hybrid",
            "organization_codes": [filters.organization_code] if filters.organization_code else None,
            "menu_date": None,
            "weekday": filters.weekday,
            "meal_type": filters.meal_type,
            "keyword": keyword,
        }

    # 남는 키워드가 없는 일반적인 질문("메뉴 알려줘" 등)은 오늘 날짜 기본 조건 검색.
    meal_type = _resolve_meal_type(filters)
    menu_date = _resolve_menu_date(filters, today)
    org_codes = _resolve_organization_codes(filters)

    return {
        "search_mode": "condition",
        "organization_codes": org_codes,
        "menu_date": menu_date,
        "weekday": filters.weekday,
        "meal_type": meal_type,
        "keyword": None,
    }


def _menu_name_part(item: str) -> str:
    """메뉴 항목 문자열에서 괄호로 시작하는 상세 설명 앞의 "메뉴 이름" 부분만 뽑는다.

    예) "오렌지치킨텐더샐러드 (구성재료: ...)" -> "오렌지치킨텐더샐러드"
    괄호가 없으면 항목 전체가 그대로 이름이다.
    """
    return item.split(" (")[0].strip()


def hybrid_search_menu(
    keyword: str,
    organization_codes: list[str] | None,
    weekday: str | None,
    meal_type: str | None,
    store: MenuFileStore,
    vector_store: VectorStore,
    top_k: int = 5,
) -> tuple[list[dict], str, dict | None]:
    """메뉴 이름/재료 키워드로 검색한다. 다음 우선순위를 순서대로 시도하고,
    앞 단계에서 하나라도 찾으면 그 결과를 바로 반환한다(뒤 단계는 시도하지 않는다).

        1. 정확 일치: 메뉴 이름이 키워드와 완전히 같음
        2. 포함: 메뉴 문자열에 키워드가 포함됨
        3. 조건 일치: 요일/끼니 조건이 있으면 그 조건으로 조회
        4. 벡터 유사도(의미 검색) - 정확한 조회의 필수 조건이 아닌 보조 수단
        5. 위에서 아무것도 못 찾으면 빈 결과

    업체가 지정된 경우(organization_codes가 비어있지 않음) 처음부터 그 업체
    데이터로만 범위를 좁혀서 검색한다.

    반환값: (결과 목록, 매칭 단계 이름, 벡터 검색이면 {entry_id: score} 아니면 None)
    """
    org_displays = (
        [ORGANIZATIONS[code]["display_name"] for code in organization_codes]
        if organization_codes
        else None
    )

    def in_scope(entry: dict) -> bool:
        return org_displays is None or entry["organization"] in org_displays

    scoped_entries = [e for e in store.get_all() if in_scope(e)]

    # 1) 정확 일치
    exact = [
        e
        for e in scoped_entries
        if any(_menu_name_part(item) == keyword for item in e["menu_items"])
    ]
    if exact:
        return exact, "exact_match", None

    # 2) 포함
    contains = [e for e in scoped_entries if any(keyword in item for item in e["menu_items"])]
    if contains:
        return contains, "contains_match", None

    # 3) 조건 일치 (요일/끼니)
    if weekday or meal_type:
        condition_hits = [
            e
            for e in store.get_by_condition(weekday=weekday, meal_type=meal_type)
            if in_scope(e)
        ]
        if condition_hits:
            return condition_hits, "condition_match", None

    # 4) 벡터 유사도 (보조 수단)
    metadata_filter = {"organization": org_displays[0]} if org_displays and len(org_displays) == 1 else None
    hits = vector_store.search(keyword, top_k=top_k, metadata_filter=metadata_filter)
    scores: dict[str, float] = {}
    vector_hits = []
    for hit in hits:
        if hit["score"] <= 0:
            continue
        entry = store.get_by_id(hit["id"])
        if entry and in_scope(entry):
            vector_hits.append(entry)
            scores[hit["id"]] = hit["score"]
    if vector_hits:
        return vector_hits, "vector_fallback", scores

    # 5) 관련성 기준을 충족하지 못함
    return [], "no_match", None


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
        # 하이브리드(메뉴명/재료) 검색에서 관련성 기준을 충족하는 메뉴를 못 찾은 경우.
        return "관련 메뉴를 찾지 못했습니다."

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
    store: MenuFileStore | None = None,
    vector_store: VectorStore | None = None,
    today: date | None = None,
    now: datetime | None = None,
) -> dict:
    """사용자의 메뉴 질문을 처리하고 통일된 결과를 반환한다.

    store: 원본 데이터를 담고 있는 MenuFileStore. 생략하면 data/menu 폴더 전체를
        읽어들인 기본 싱글턴을 쓴다(menu.db는 만들지 않는다). 테스트에서는
        tmp 디렉터리를 가리키는 MenuFileStore를 만들어 주입할 수 있다.
    vector_store: 의미 검색에만 쓰는 보조 저장소. 생략하면 기본(영구 저장)
        싱글턴을 쓴다. 정확한 날짜/업체 조회에는 관여하지 않는다.
    now/today: 기준 시각/날짜. 생략하면 한국 시간 기준 현재 값을 쓴다.

    반환값은 항상 다음 형태를 유지한다 (예외가 발생해도 동일).
    {"success": bool, "query": str, "results": list[dict], "answer": str}
    """
    store = store or get_store()
    vector_store = vector_store or get_vector_store()
    now = now or get_now_kst()
    today = today or now.date()

    try:
        filters = parse_query(query, today=today)
        plan = plan_menu_search(query, filters, today)
        search_mode = plan["search_mode"]

        if search_mode == "hybrid":
            raw_results, _match_tier, _scores = hybrid_search_menu(
                plan["keyword"],
                plan["organization_codes"],
                plan["weekday"],
                plan["meal_type"],
                store,
                vector_store,
            )
        else:
            # 해당 조건에 데이터가 없어도 다른 날짜/끼니/업체로 대체하지 않는다.
            org_display_list = [
                ORGANIZATIONS[code]["display_name"] for code in plan["organization_codes"]
            ]
            raw_results = []
            for org_display in org_display_list:
                raw_results.extend(
                    store.get_by_condition(
                        organization=org_display,
                        menu_date=plan["menu_date"],
                        weekday=plan["weekday"],
                        meal_type=plan["meal_type"],
                    )
                )

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
