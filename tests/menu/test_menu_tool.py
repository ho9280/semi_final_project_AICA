"""menu_tool.py에 대한 테스트.

get_menu()/get_current_menu()는 data/menu 폴더 구조를 그대로 흉내 낸 tmp_path
아래(daesung/kt/kt_salad 폴더)에서 MenuFileStore로 읽어들여 검증한다.
SQLite(menu.db)는 이 경로에서 전혀 쓰이지 않는다.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from PIL import Image

from app.menu.config import KST
from app.menu.menu_agent import query_menu
from app.menu.menu_embedding import VectorStore
from app.menu.menu_file_store import MenuFileStore
from app.menu.menu_tool import get_current_menu, get_menu

TODAY = date(2026, 7, 22)  # 수요일
MORNING = datetime(2026, 7, 22, 9, 0, tzinfo=KST)
AFTERNOON = datetime(2026, 7, 22, 15, 0, tzinfo=KST)
NIGHT = datetime(2026, 7, 22, 20, 0, tzinfo=KST)


def _write_sample_image(folder, filename: str, ocr_text: str):
    folder.mkdir(parents=True, exist_ok=True)
    image_path = folder / f"{filename}.png"
    Image.new("RGB", (4, 4), color=(255, 255, 255)).save(image_path)
    (folder / f"{filename}.txt").write_text(ocr_text, encoding="utf-8")
    return image_path


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "data"


def _build_store(data_dir) -> MenuFileStore:
    store = MenuFileStore(data_dir=data_dir)
    store.load()
    return store


@pytest.fixture
def vector_store(tmp_path):
    return VectorStore(store_path=tmp_path / "vector_store.json")


# ---------- get_menu (챗봇) ----------


def test_get_menu_returns_fixed_schema_keys(data_dir, vector_store):
    store = _build_store(data_dir)
    result = get_menu("오늘 KT 메뉴 뭐야?", now=MORNING, store=store, vector_store=vector_store)
    assert set(result.keys()) == {"success", "query", "conditions", "results", "answer", "error"}
    assert set(result["conditions"].keys()) == {
        "organization",
        "menu_date",
        "weekday",
        "meal_type",
        "search_mode",
    }


def test_get_menu_success_has_no_error(data_dir, vector_store):
    _write_sample_image(
        data_dir / "kt", "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치"
    )
    store = _build_store(data_dir)

    result = get_menu("오늘 KT 메뉴 뭐야?", now=MORNING, store=store, vector_store=vector_store)

    assert result["success"] is True
    assert result["error"] is None
    assert result["conditions"]["organization"] == "KT"
    assert result["conditions"]["menu_date"] == "2026-07-22"
    assert result["conditions"]["meal_type"] == "점심"
    assert result["conditions"]["search_mode"] == "condition"


def test_get_menu_result_contains_required_fields(data_dir, vector_store):
    image = _write_sample_image(
        data_dir / "kt", "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치"
    )
    store = _build_store(data_dir)

    result = get_menu("오늘 KT 메뉴 뭐야?", now=MORNING, store=store, vector_store=vector_store)

    entry = result["results"][0]
    assert entry["organization"] == "KT"
    assert entry["menu_date"] == "2026-07-22"
    assert entry["weekday"] == "수요일"
    assert entry["meal_type"] == "점심"
    assert entry["menu_items"] == ["제육볶음", "미역국", "배추김치"]
    assert entry["source_image_path"] == str(image)


def test_get_menu_no_data_returns_failure_without_error(data_dir, vector_store):
    store = _build_store(data_dir)
    result = get_menu("오늘 KT 메뉴 뭐야?", now=MORNING, store=store, vector_store=vector_store)

    assert result["success"] is False
    assert result["results"] == []
    assert result["error"] is None
    assert result["answer"] == "해당 날짜에는 등록된 식단이 없습니다."


def test_get_menu_matches_query_menu_output(data_dir, vector_store):
    _write_sample_image(data_dir / "daesung", "daesung_menu", "2026-07-22 수요일 점심: 비빔밥, 계란국")
    store = _build_store(data_dir)

    tool_result = get_menu("오늘 대성 메뉴 알려줘", now=MORNING, store=store, vector_store=vector_store)
    direct_result = query_menu(
        "오늘 대성 메뉴 알려줘", store=store, vector_store=vector_store, now=MORNING
    )

    assert tool_result["success"] == direct_result["success"]
    assert tool_result["query"] == direct_result["query"]
    assert tool_result["results"] == direct_result["results"]
    assert tool_result["answer"] == direct_result["answer"]


def test_get_menu_meal_type_ignores_time_of_day(data_dir, vector_store):
    # 최종 정의서: 챗봇은 끼니를 지정하지 않으면 시각과 무관하게 항상 중식(점심)이다.
    _write_sample_image(
        data_dir / "daesung",
        "daesung_menu",
        "\n".join(
            [
                "2026-07-22 수요일 점심: 비빔밥, 계란국",
                "2026-07-22 수요일 저녁: 삼겹살, 상추쌈",
            ]
        ),
    )
    store = _build_store(data_dir)

    for now in (MORNING, AFTERNOON, NIGHT):
        result = get_menu("오늘 대성 메뉴 알려줘", now=now, store=store, vector_store=vector_store)
        assert result["conditions"]["meal_type"] == "점심", now
        assert result["results"][0]["menu_items"] == ["비빔밥", "계란국"]


def test_get_menu_without_organization_includes_all_three(data_dir, vector_store):
    _write_sample_image(data_dir / "kt", "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국")
    _write_sample_image(data_dir / "daesung", "daesung_menu", "2026-07-22 수요일 점심: 돈가스, 스프")
    _write_sample_image(
        data_dir / "kt_salad", "salad_menu", "2026-07-22 수요일 점심: 닭가슴살샐러드, 고구마"
    )
    store = _build_store(data_dir)

    result = get_menu("오늘 메뉴 알려줘", now=MORNING, store=store, vector_store=vector_store)

    orgs = {r["organization"] for r in result["results"]}
    assert orgs == {"KT", "대성학원", "KT 샐러드"}


def test_get_menu_uses_current_time_when_now_omitted(data_dir, vector_store):
    store = _build_store(data_dir)
    result = get_menu("오늘 KT 메뉴 뭐야?", store=store, vector_store=vector_store)
    assert set(result.keys()) == {"success", "query", "conditions", "results", "answer", "error"}


# ---------- get_current_menu (대시보드) ----------


def _write_daesung_lunch_and_dinner(data_dir):
    _write_sample_image(
        data_dir / "daesung",
        "daesung_menu",
        "\n".join(
            [
                "2026-07-22 수요일 점심: 비빔밥, 계란국",
                "2026-07-22 수요일 저녁: 삼겹살, 상추쌈",
                "2026-07-23 목요일 점심: 돈까스, 우동",
            ]
        ),
    )


def test_get_current_menu_before_13h_returns_lunch_all_three(data_dir):
    _write_daesung_lunch_and_dinner(data_dir)
    _write_sample_image(data_dir / "kt", "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국")
    _write_sample_image(
        data_dir / "kt_salad", "salad_menu", "2026-07-22 수요일 점심: 닭가슴살샐러드, 고구마"
    )
    store = _build_store(data_dir)

    result = get_current_menu(now=MORNING, store=store)

    assert result["success"] is True
    assert result["conditions"]["meal_type"] == "점심"
    assert result["conditions"]["menu_date"] == "2026-07-22"
    orgs = {r["organization"] for r in result["results"]}
    assert orgs == {"대성학원", "KT", "KT 샐러드"}


def test_get_current_menu_13_to_19h_returns_daesung_dinner_only(data_dir):
    _write_daesung_lunch_and_dinner(data_dir)
    _write_sample_image(data_dir / "kt", "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국")
    store = _build_store(data_dir)

    result = get_current_menu(now=AFTERNOON, store=store)

    assert result["success"] is True
    assert result["conditions"]["meal_type"] == "저녁"
    assert len(result["results"]) == 1
    assert result["results"][0]["organization"] == "대성학원"
    assert result["results"][0]["menu_items"] == ["삼겹살", "상추쌈"]


def test_get_current_menu_after_19h_returns_next_day_lunch_all_three(data_dir):
    _write_daesung_lunch_and_dinner(data_dir)
    _write_sample_image(
        data_dir / "kt", "kt_menu_next", "2026-07-23 목요일 점심: 돈까스, 우동, 단무지"
    )
    _write_sample_image(
        data_dir / "kt_salad", "salad_menu_next", "2026-07-23 목요일 점심: 참치샐러드, 삶은계란"
    )
    store = _build_store(data_dir)

    result = get_current_menu(now=NIGHT, store=store)

    assert result["success"] is True
    assert result["conditions"]["meal_type"] == "점심"
    assert result["conditions"]["menu_date"] == "2026-07-23"
    orgs = {r["organization"] for r in result["results"]}
    assert orgs == {"대성학원", "KT", "KT 샐러드"}
    assert all(r["menu_date"] == "2026-07-23" for r in result["results"])


def test_get_current_menu_no_data_returns_no_data_message(data_dir):
    store = _build_store(data_dir)
    result = get_current_menu(now=MORNING, store=store)

    assert result["success"] is False
    assert result["results"] == []
    assert result["answer"] == "해당 날짜에는 등록된 식단이 없습니다."


def test_get_current_menu_returns_fixed_schema_keys(data_dir):
    store = _build_store(data_dir)
    result = get_current_menu(now=MORNING, store=store)
    assert set(result.keys()) == {"success", "query", "conditions", "results", "answer", "error"}
