"""menu_agent.py에 대한 통합 테스트.

OCR은 MockOCRProvider(sidecar .txt 파일)를 사용하므로 실제 OCR 엔진 없이도
전체 흐름(이미지 등록 -> 저장 -> 질문 -> 답변)을 검증할 수 있다.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from PIL import Image

from app.menu.config import KST
from app.menu.menu_agent import parse_query, query_menu, register_menu_image
from app.menu.menu_embedding import VectorStore
from app.menu.menu_repository import MenuRepository

TODAY = date(2026, 7, 22)  # 수요일

# 끼니를 지정하지 않은 질문의 기본값이 시간대에 따라 달라지므로, 시간에 의존하지 않는
# 테스트에서는 항상 이 기준 시각(오전 9시 = 점심 시간대)을 명시적으로 전달한다.
MORNING = datetime(2026, 7, 22, 9, 0, tzinfo=KST)


def _write_sample_image(tmp_path, filename: str, ocr_text: str):
    image_path = tmp_path / f"{filename}.png"
    Image.new("RGB", (4, 4), color=(255, 255, 255)).save(image_path)
    (tmp_path / f"{filename}.txt").write_text(ocr_text, encoding="utf-8")
    return image_path


@pytest.fixture
def repo(tmp_path):
    return MenuRepository(db_path=tmp_path / "menu.db")


@pytest.fixture
def vector_store(tmp_path):
    return VectorStore(store_path=tmp_path / "vector_store.json")


# ---------- 질문 분석 ----------


def test_parse_query_extracts_organization_and_today():
    filters = parse_query("오늘 KT 메뉴 뭐야?", today=TODAY)
    assert filters.organization_display == "KT"
    assert filters.menu_date == "2026-07-22"


def test_parse_query_extracts_tomorrow_and_daesung():
    filters = parse_query("내일 대성학원 점심 알려줘.", today=TODAY)
    assert filters.organization_display == "대성학원"
    assert filters.menu_date == "2026-07-23"
    assert filters.meal_type == "점심"


def test_parse_query_kt_salad_alias_not_confused_with_kt():
    filters = parse_query("KT 샐러드 메뉴 알려줘.", today=TODAY)
    assert filters.organization_display == "KT 샐러드"


def test_parse_query_no_organization_when_absent():
    filters = parse_query("오늘 식단 알려줘.", today=TODAY)
    assert filters.organization_display is None
    assert filters.menu_date == "2026-07-22"


# ---------- 등록(OCR -> 구조화 -> 저장) ----------


def test_register_menu_image_success(tmp_path, repo, vector_store):
    image = _write_sample_image(
        tmp_path, "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치"
    )

    result = register_menu_image(image, "kt", repository=repo, vector_store=vector_store)

    assert result["success"] is True
    assert len(result["registered_ids"]) == 1
    assert repo.count() == 1
    assert vector_store.count() == 1


def test_register_menu_image_ocr_failure_without_sidecar(tmp_path, repo, vector_store):
    image_path = tmp_path / "no_sidecar.png"
    Image.new("RGB", (4, 4)).save(image_path)

    result = register_menu_image(image_path, "kt", repository=repo, vector_store=vector_store)

    assert result["success"] is False
    assert result["error"] == "OCR 결과 없음"
    assert result["registered_ids"] == []


def test_register_menu_image_unknown_organization(tmp_path, repo, vector_store):
    image = _write_sample_image(tmp_path, "x", "아무 텍스트")
    result = register_menu_image(image, "unknown_org", repository=repo, vector_store=vector_store)
    assert result["success"] is False
    assert "알 수 없는 업체" in result["error"]


def test_register_menu_image_duplicate_does_not_grow_storage(tmp_path, repo, vector_store):
    image = _write_sample_image(
        tmp_path, "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치"
    )
    register_menu_image(image, "kt", repository=repo, vector_store=vector_store)
    register_menu_image(image, "kt", repository=repo, vector_store=vector_store)

    assert repo.count() == 1
    assert vector_store.count() == 1


# ---------- query_menu 통합 ----------


def test_query_menu_exact_organization_and_date(tmp_path, repo, vector_store):
    image = _write_sample_image(
        tmp_path, "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치"
    )
    register_menu_image(image, "kt", repository=repo, vector_store=vector_store)

    result = query_menu("오늘 KT 메뉴 뭐야?", repository=repo, vector_store=vector_store, today=TODAY, now=MORNING)

    assert result["success"] is True
    assert result["query"] == "오늘 KT 메뉴 뭐야?"
    assert len(result["results"]) == 1
    r = result["results"][0]
    assert r["organization"] == "KT"
    assert r["menu_items"] == ["제육볶음", "미역국", "배추김치"]
    assert r["source_image_path"] == str(image)
    assert "제육볶음" in result["answer"]


def test_query_menu_without_organization_returns_all(tmp_path, repo, vector_store):
    kt_image = _write_sample_image(
        tmp_path, "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치"
    )
    daesung_image = _write_sample_image(
        tmp_path, "daesung_menu", "2026-07-22 수요일 점심: 돈가스, 스프, 양배추샐러드"
    )
    register_menu_image(kt_image, "kt", repository=repo, vector_store=vector_store)
    register_menu_image(daesung_image, "daesung", repository=repo, vector_store=vector_store)

    result = query_menu("오늘 식단 알려줘.", repository=repo, vector_store=vector_store, today=TODAY, now=MORNING)

    assert result["success"] is True
    assert len(result["results"]) == 2
    orgs = {r["organization"] for r in result["results"]}
    assert orgs == {"KT", "대성학원"}


def test_query_menu_semantic_search_finds_menu_item(tmp_path, repo, vector_store):
    daesung_image = _write_sample_image(
        tmp_path,
        "daesung_menu",
        "\n".join(
            [
                "2026-07-20 월요일 점심: 비빔밥, 계란국",
                "2026-07-23 목요일 점심: 돈가스, 우동, 단무지",
            ]
        ),
    )
    register_menu_image(daesung_image, "daesung", repository=repo, vector_store=vector_store)

    result = query_menu(
        "이번 주에 돈가스 나오는 날이 언제야?",
        repository=repo,
        vector_store=vector_store,
        today=TODAY,
    )

    assert result["success"] is True
    assert any("돈가스" in r["menu_items"] for r in result["results"])


def test_query_menu_no_results_returns_failure_structure(tmp_path, repo, vector_store):
    result = query_menu("오늘 KT 메뉴 뭐야?", repository=repo, vector_store=vector_store, today=TODAY, now=MORNING)

    assert result["success"] is False
    assert result["results"] == []
    assert result["answer"] == "해당 날짜에는 등록된 식단이 없습니다."


def test_query_menu_always_returns_same_shape_keys(tmp_path, repo, vector_store):
    result = query_menu("아무 의미 없는 질문", repository=repo, vector_store=vector_store, today=TODAY, now=MORNING)
    assert set(result.keys()) == {"success", "query", "results", "answer"}


# ---------- 6단계: 기본 조회 조건 및 예외 처리 ----------


def test_query_menu_defaults_meal_type_to_lunch_when_unspecified(tmp_path, repo, vector_store):
    image = _write_sample_image(
        tmp_path, "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치"
    )
    register_menu_image(image, "kt", repository=repo, vector_store=vector_store)

    # "끼니"를 언급하지 않아도 중식(점심)이 기본값으로 적용되어 조회되어야 한다.
    result = query_menu("오늘 KT 메뉴 뭐야?", repository=repo, vector_store=vector_store, today=TODAY, now=MORNING)

    assert result["success"] is True
    assert result["results"][0]["meal_type"] == "점심"


def test_query_menu_without_organization_returns_daesung_and_kt_only(tmp_path, repo, vector_store):
    kt_image = _write_sample_image(
        tmp_path, "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치"
    )
    daesung_image = _write_sample_image(
        tmp_path, "daesung_menu", "2026-07-22 수요일 점심: 돈가스, 스프, 양배추샐러드"
    )
    salad_image = _write_sample_image(
        tmp_path, "salad_menu", "2026-07-22 수요일 점심: 닭가슴살샐러드, 고구마"
    )
    register_menu_image(kt_image, "kt", repository=repo, vector_store=vector_store)
    register_menu_image(daesung_image, "daesung", repository=repo, vector_store=vector_store)
    register_menu_image(salad_image, "kt_salad", repository=repo, vector_store=vector_store)

    result = query_menu("오늘 식단 알려줘.", repository=repo, vector_store=vector_store, today=TODAY, now=MORNING)

    orgs = {r["organization"] for r in result["results"]}
    assert orgs == {"KT", "대성학원"}
    assert "KT 샐러드" not in orgs


def test_query_menu_returns_salad_only_when_explicitly_requested(tmp_path, repo, vector_store):
    salad_image = _write_sample_image(
        tmp_path, "salad_menu", "2026-07-22 수요일 점심: 닭가슴살샐러드, 고구마"
    )
    kt_image = _write_sample_image(
        tmp_path, "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치"
    )
    register_menu_image(salad_image, "kt_salad", repository=repo, vector_store=vector_store)
    register_menu_image(kt_image, "kt", repository=repo, vector_store=vector_store)

    result = query_menu(
        "오늘 KT 샐러드 메뉴 알려줘.",
        repository=repo,
        vector_store=vector_store,
        today=TODAY,
        now=MORNING,
    )

    assert result["success"] is True
    assert len(result["results"]) == 1
    assert result["results"][0]["organization"] == "KT 샐러드"


def test_query_menu_does_not_fallback_to_other_date(tmp_path, repo, vector_store):
    # 7/23(내일) 메뉴만 등록하고 "오늘" 메뉴를 조회하면, 다른 날짜 메뉴로 대체되면 안 된다.
    image = _write_sample_image(
        tmp_path, "kt_menu", "2026-07-23 목요일 점심: 돈까스, 우동, 단무지"
    )
    register_menu_image(image, "kt", repository=repo, vector_store=vector_store)

    result = query_menu("오늘 KT 메뉴 뭐야?", repository=repo, vector_store=vector_store, today=TODAY, now=MORNING)

    assert result["success"] is False
    assert result["results"] == []
    assert result["answer"] == "해당 날짜에는 등록된 식단이 없습니다."


def test_query_menu_no_data_message_for_default_organizations(tmp_path, repo, vector_store):
    result = query_menu("오늘 식단 알려줘.", repository=repo, vector_store=vector_store, today=TODAY, now=MORNING)

    assert result["success"] is False
    assert result["results"] == []
    assert result["answer"] == "해당 날짜에는 등록된 식단이 없습니다."


# ---------- 7단계: 석식 구분 및 시간대별 식단 조회 ----------

AFTERNOON = datetime(2026, 7, 22, 15, 0, tzinfo=KST)  # 13시~19시 구간
NIGHT = datetime(2026, 7, 22, 20, 0, tzinfo=KST)  # 19시 이후 구간


def _register_daesung_lunch_and_dinner(tmp_path, repo, vector_store):
    image = _write_sample_image(
        tmp_path,
        "daesung_menu",
        "\n".join(
            [
                "2026-07-22 수요일 점심: 비빔밥, 계란국",
                "2026-07-22 수요일 저녁: 삼겹살, 상추쌈",
            ]
        ),
    )
    register_menu_image(image, "daesung", repository=repo, vector_store=vector_store)


def test_meal_type_synonyms_lunch_return_same_menu(tmp_path, repo, vector_store):
    image = _write_sample_image(
        tmp_path, "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치"
    )
    register_menu_image(image, "kt", repository=repo, vector_store=vector_store)

    for word in ["점심", "중식", "런치"]:
        result = query_menu(
            f"오늘 KT {word} 알려줘",
            repository=repo,
            vector_store=vector_store,
            today=TODAY,
            now=MORNING,
        )
        assert result["success"] is True, word
        assert result["results"][0]["meal_type"] == "점심"
        assert result["results"][0]["menu_items"] == ["제육볶음", "미역국", "배추김치"]


def test_meal_type_synonyms_dinner_return_same_menu(tmp_path, repo, vector_store):
    _register_daesung_lunch_and_dinner(tmp_path, repo, vector_store)

    for word in ["저녁", "석식", "디너"]:
        result = query_menu(
            f"오늘 대성 {word} 알려줘",
            repository=repo,
            vector_store=vector_store,
            today=TODAY,
            now=MORNING,
        )
        assert result["success"] is True, word
        assert result["results"][0]["meal_type"] == "저녁"
        assert result["results"][0]["menu_items"] == ["삼겹살", "상추쌈"]


def test_daesung_lunch_and_dinner_are_distinguished(tmp_path, repo, vector_store):
    _register_daesung_lunch_and_dinner(tmp_path, repo, vector_store)

    lunch_result = query_menu(
        "오늘 대성 점심 알려줘", repository=repo, vector_store=vector_store, today=TODAY, now=MORNING
    )
    dinner_result = query_menu(
        "오늘 대성 저녁 알려줘", repository=repo, vector_store=vector_store, today=TODAY, now=MORNING
    )

    assert lunch_result["results"][0]["menu_items"] == ["비빔밥", "계란국"]
    assert dinner_result["results"][0]["menu_items"] == ["삼겹살", "상추쌈"]


def test_explicit_meal_type_overrides_time_window_default(tmp_path, repo, vector_store):
    _register_daesung_lunch_and_dinner(tmp_path, repo, vector_store)

    # 오후 3시(저녁 시간대)지만 사용자가 "중식"(점심)을 직접 지정했으므로 점심이 나와야 한다.
    result = query_menu(
        "오늘 대성 중식 알려줘", repository=repo, vector_store=vector_store, today=TODAY, now=AFTERNOON
    )

    assert result["success"] is True
    assert result["results"][0]["meal_type"] == "점심"
    assert result["results"][0]["menu_items"] == ["비빔밥", "계란국"]


def test_time_window_before_13h_defaults_to_lunch(tmp_path, repo, vector_store):
    _register_daesung_lunch_and_dinner(tmp_path, repo, vector_store)
    kt_image = _write_sample_image(
        tmp_path, "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치"
    )
    register_menu_image(kt_image, "kt", repository=repo, vector_store=vector_store)

    # 끼니를 지정하지 않고 오전 9시에 물으면 당일 점심(대성학원+KT)이 나와야 한다.
    result = query_menu(
        "메뉴 알려줘", repository=repo, vector_store=vector_store, today=TODAY, now=MORNING
    )

    assert result["success"] is True
    orgs = {r["organization"] for r in result["results"]}
    assert orgs == {"대성학원", "KT"}
    assert all(r["meal_type"] == "점심" for r in result["results"])
    assert all(r["menu_date"] == "2026-07-22" for r in result["results"])


def test_time_window_13_to_19h_defaults_to_daesung_dinner(tmp_path, repo, vector_store):
    _register_daesung_lunch_and_dinner(tmp_path, repo, vector_store)
    kt_image = _write_sample_image(
        tmp_path, "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치"
    )
    register_menu_image(kt_image, "kt", repository=repo, vector_store=vector_store)

    # 끼니를 지정하지 않고 오후 3시에 물으면 당일 "대성학원 저녁"만 나와야 한다 (KT는 저녁 데이터가 없음).
    result = query_menu(
        "메뉴 알려줘", repository=repo, vector_store=vector_store, today=TODAY, now=AFTERNOON
    )

    assert result["success"] is True
    assert len(result["results"]) == 1
    assert result["results"][0]["organization"] == "대성학원"
    assert result["results"][0]["meal_type"] == "저녁"
    assert result["results"][0]["menu_items"] == ["삼겹살", "상추쌈"]


def test_time_window_after_19h_defaults_to_next_day_lunch(tmp_path, repo, vector_store):
    tomorrow_image = _write_sample_image(
        tmp_path, "kt_menu_next", "2026-07-23 목요일 점심: 돈까스, 우동, 단무지"
    )
    register_menu_image(tomorrow_image, "kt", repository=repo, vector_store=vector_store)
    # 오늘(수요일) 점심 데이터도 함께 등록해, 오늘 것이 아니라 "다음 식단 제공일"(내일) 것이
    # 선택되는지 구분해서 확인한다.
    today_image = _write_sample_image(
        tmp_path, "kt_menu_today", "2026-07-22 수요일 점심: 제육볶음, 미역국"
    )
    register_menu_image(today_image, "kt", repository=repo, vector_store=vector_store)

    # 끼니를 지정하지 않고 밤 8시에 물으면 "다음 식단 제공일"인 내일(7/23) 점심이 나와야 한다.
    result = query_menu(
        "KT 메뉴 뭐야?",
        repository=repo,
        vector_store=vector_store,
        today=TODAY,
        now=NIGHT,
    )

    assert result["success"] is True
    assert result["results"][0]["menu_date"] == "2026-07-23"
    assert result["results"][0]["menu_items"] == ["돈까스", "우동", "단무지"]


def test_kt_dinner_not_registered_returns_no_data_message(tmp_path, repo, vector_store):
    # KT는 저녁 데이터가 없으므로, 저녁을 직접 요청해도 임의로 다른 메뉴를 대신 반환하지 않는다.
    image = _write_sample_image(
        tmp_path, "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치"
    )
    register_menu_image(image, "kt", repository=repo, vector_store=vector_store)

    result = query_menu(
        "오늘 KT 저녁 알려줘", repository=repo, vector_store=vector_store, today=TODAY, now=MORNING
    )

    assert result["success"] is False
    assert result["results"] == []
    assert result["answer"] == "해당 날짜에는 등록된 식단이 없습니다."
