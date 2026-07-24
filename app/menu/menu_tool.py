"""다른 팀(다른 Agent, FastAPI 라우터, LangGraph Router)이 import해서 쓰는
공개 Menu Tool 인터페이스.

이 파일은 새로운 검색 로직을 구현하지 않는다.

- 챗봇 질문(``get_menu``)은 ``menu_agent.query_menu()``/``plan_menu_search()``를
  그대로 재사용한다.
- 대시보드 자동 표시(``get_current_menu``)는 시간대에 따라 오늘/내일, 점심/저녁,
  조회 업체를 정하는 별도의 규칙을 쓴다(챗봇과는 다른 목적이라 분리했다).
- 새 식단표를 추가한 뒤 다시 불러오는 ``reload_menu_data``는
  ``menu_file_store.py``의 구현을 그대로 다시 내보낸다(re-export).

원본 데이터는 SQLite가 아니라 ``data/menu/`` 폴더의 이미지 + .txt(sidecar)다.
기본 실행 경로에서는 ``menu.db``를 만들지 않는다.

사용 예시:
    from app.menu.menu_tool import get_menu, get_current_menu, reload_menu_data

    reload_menu_data()
    result = get_menu("오늘 KT 메뉴 뭐야?")
    dashboard_result = get_current_menu()
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from app.menu.config import DEFAULT_ORGANIZATION_CODES, DINNER_ORGANIZATION_CODES, ORGANIZATIONS
from app.menu.menu_agent import (
    _strip_internal_fields,
    get_now_kst,
    parse_query,
    plan_menu_search,
    query_menu,
)
from app.menu.menu_embedding import VectorStore
from app.menu.menu_file_store import MenuFileStore, get_store, reload_menu_data  # noqa: F401 (re-export)

__all__ = ["get_menu", "get_current_menu", "reload_menu_data"]


def _organization_names(codes: list[str] | None) -> list[str] | None:
    if not codes:
        return None
    return [ORGANIZATIONS[code]["display_name"] for code in codes]


def _build_conditions(query: str, today: date) -> dict:
    """query_menu()가 실제로 어떤 조건(업체/날짜/요일/끼니)으로 조회했는지
    설명하는 정보를 만든다. 검색 로직 자체는 plan_menu_search()를 그대로
    재사용하므로 여기서 다시 구현하지 않는다.
    """
    filters = parse_query(query, today=today)
    plan = plan_menu_search(query, filters, today)

    organization = (
        filters.organization_display
        if filters.organization_code
        else _organization_names(plan["organization_codes"])
    )

    return {
        "organization": organization,
        "menu_date": plan["menu_date"],
        "weekday": plan["weekday"],
        "meal_type": plan["meal_type"],
        "search_mode": plan["search_mode"],
    }


def get_menu(
    query: str,
    now: datetime | None = None,
    store: MenuFileStore | None = None,
    vector_store: VectorStore | None = None,
) -> dict:
    """사용자의 메뉴 질문(챗봇)을 처리하고, 팀 간 계약에 맞는 고정된 결과를 반환한다.

    query: 사용자 질문 문자열 (예: "오늘 KT 메뉴 뭐야?")
    now: 검색 기준 시각(선택). 테스트에서 특정 시각을 고정하고 싶을 때 전달한다.
         생략하면 한국 시간 기준 현재 시각을 사용한다.
    store/vector_store: 테스트용 의존성 주입(선택). 생략하면 data/menu 폴더 전체를
         읽어들인 기본 싱글턴을 사용하며, menu.db는 만들지 않는다.

    끼니를 지정하지 않으면 현재 시각과 무관하게 항상 "점심"(중식)을 기본값으로
    조회한다. 시간대별 기본값이 필요하면 ``get_current_menu()``(대시보드용)를
    사용한다.

    반환값은 예외가 발생해도 항상 다음 형태를 유지한다.
        {
            "success": bool,
            "query": str,
            "conditions": {
                "organization": str | list[str] | None,
                "menu_date": str | None,
                "weekday": str | None,
                "meal_type": str | None,
                "search_mode": "condition" | "hybrid",
            },
            "results": [
                {
                    "organization": str, "menu_type": str, "menu_date": str,
                    "weekday": str, "meal_type": str, "menu_items": list[str],
                    "source_image_path": str,
                },
                ...
            ],
            "answer": str,
            "error": str | None,
        }
    """
    now = now or get_now_kst()
    today = now.date()

    try:
        conditions = _build_conditions(query, today)
        result = query_menu(query, store=store, vector_store=vector_store, today=today, now=now)

        return {
            "success": result["success"],
            "query": result["query"],
            "conditions": conditions,
            "results": result["results"],
            "answer": result["answer"],
            "error": None,
        }
    except Exception as exc:  # 어떤 예외가 나도 동일한 스키마를 유지한다.
        return {
            "success": False,
            "query": query,
            "conditions": {},
            "results": [],
            "answer": f"메뉴 조회 중 오류가 발생했습니다: {exc}",
            "error": str(exc),
        }


def get_current_menu(now: datetime | None = None, store: MenuFileStore | None = None) -> dict:
    """대시보드에 자동으로 표시할 "지금 시각 기준" 메뉴를 반환한다.

    챗봇 질문(``get_menu``)과는 목적이 달라 시간대별 기본값을 따로 적용한다.

        00:00 ~ 12:59  당일 점심,  대성학원 + KT + KT 샐러드
        13:00 ~ 18:59  당일 저녁,  대성학원만 (KT/KT 샐러드는 저녁 데이터 없음)
        19:00 ~ 23:59  다음날 점심, 대성학원 + KT + KT 샐러드

    now: 기준 시각(선택). 테스트에서 특정 시각을 고정할 때 전달한다. 생략하면
        한국 시간 기준 현재 시각을 사용한다.
    store: 테스트용 의존성 주입(선택). 생략하면 기본 싱글턴을 사용한다.

    반환값 스키마는 ``get_menu()``와 동일하게 유지한다
    (success/query/conditions/results/answer/error).
    """
    now = now or get_now_kst()
    today = now.date()
    store = store or get_store()

    try:
        hour = now.hour
        if 0 <= hour < 13:
            meal_type = "점심"
            menu_date = today.isoformat()
            org_codes = DEFAULT_ORGANIZATION_CODES
        elif 13 <= hour < 19:
            meal_type = "저녁"
            menu_date = today.isoformat()
            org_codes = DINNER_ORGANIZATION_CODES
        else:
            meal_type = "점심"
            menu_date = (today + timedelta(days=1)).isoformat()
            org_codes = DEFAULT_ORGANIZATION_CODES

        raw_results = []
        for code in org_codes:
            org_display = ORGANIZATIONS[code]["display_name"]
            raw_results.extend(
                store.get_by_condition(organization=org_display, menu_date=menu_date, meal_type=meal_type)
            )

        results = [_strip_internal_fields(r) for r in raw_results]

        conditions = {
            "organization": _organization_names(org_codes),
            "menu_date": menu_date,
            "weekday": None,
            "meal_type": meal_type,
            "search_mode": "dashboard",
        }

        if not results:
            answer = "해당 날짜에는 등록된 식단이 없습니다."
        else:
            lines = [
                f"[{r['organization']}] {r['meal_type']}: {', '.join(r['menu_items'])}" for r in results
            ]
            answer = "\n".join(lines)

        return {
            "success": len(results) > 0,
            "query": "(대시보드 자동 조회)",
            "conditions": conditions,
            "results": results,
            "answer": answer,
            "error": None,
        }
    except Exception as exc:  # 어떤 예외가 나도 동일한 스키마를 유지한다.
        return {
            "success": False,
            "query": "(대시보드 자동 조회)",
            "conditions": {},
            "results": [],
            "answer": f"메뉴 조회 중 오류가 발생했습니다: {exc}",
            "error": str(exc),
        }
