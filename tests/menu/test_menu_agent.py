"""menu_agent.py에 대한 통합 테스트.

최종 정의서 기준으로 챗봇 질문(query_menu)의 기본 데이터 원본은
data/menu 폴더의 이미지 + .txt(sidecar)이다(SQLite 아님). 테스트에서는
tmp_path 아래에 업체 폴더(daesung/kt/kt_salad)를 만들고 MenuFileStore로
읽어들여 실제 파일 배치와 최대한 비슷하게 검증한다.

register_menu_image()/MenuRepository(SQLite)는 호환용으로 남아 있으므로
별도 절에서 그대로 계속 테스트한다.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from PIL import Image

from app.menu.config import KST
from app.menu.menu_agent import (
    parse_query,
    plan_menu_search,
    query_menu,
    register_menu_image,
)
from app.menu.menu_embedding import VectorStore
from app.menu.menu_file_store import MenuFileStore
from app.menu.menu_repository import MenuRepository

TODAY = date(2026, 7, 22)  # 수요일
NOW = datetime(2026, 7, 22, 9, 0, tzinfo=KST)  # 시각은 챗봇 기본값에 영향을 주지 않는다.


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


# ---------- SQLite 등록 경로 (호환용, register_menu_image) ----------


def _write_sqlite_sample_image(tmp_path, filename: str, ocr_text: str):
    image_path = tmp_path / f"{filename}.png"
    Image.new("RGB", (4, 4), color=(255, 255, 255)).save(image_path)
    (tmp_path / f"{filename}.txt").write_text(ocr_text, encoding="utf-8")
    return image_path


@pytest.fixture
def repo(tmp_path):
    return MenuRepository(db_path=tmp_path / "menu.db")


def test_register_menu_image_success(tmp_path, repo, vector_store):
    image = _write_sqlite_sample_image(
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
    image = _write_sqlite_sample_image(tmp_path, "x", "아무 텍스트")
    result = register_menu_image(image, "unknown_org", repository=repo, vector_store=vector_store)
    assert result["success"] is False
    assert "알 수 없는 업체" in result["error"]


def test_register_menu_image_duplicate_does_not_grow_storage(tmp_path, repo, vector_store):
    image = _write_sqlite_sample_image(
        tmp_path, "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치"
    )
    register_menu_image(image, "kt", repository=repo, vector_store=vector_store)
    register_menu_image(image, "kt", repository=repo, vector_store=vector_store)

    assert repo.count() == 1
    assert vector_store.count() == 1


# ---------- plan_menu_search / query_menu (파일 기반 챗봇 경로) ----------


def test_plan_menu_search_defaults_to_lunch_regardless_of_time():
    filters = parse_query("KT 메뉴 알려줘", today=TODAY)
    plan = plan_menu_search("KT 메뉴 알려줘", filters, TODAY)
    assert plan["meal_type"] == "점심"


def test_query_menu_exact_organization_and_date(data_dir, vector_store):
    image = _write_sample_image(
        data_dir / "kt", "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치"
    )
    store = _build_store(data_dir)

    result = query_menu("오늘 KT 메뉴 뭐야?", store=store, vector_store=vector_store, today=TODAY, now=NOW)

    assert result["success"] is True
    assert result["query"] == "오늘 KT 메뉴 뭐야?"
    assert len(result["results"]) == 1
    r = result["results"][0]
    assert r["organization"] == "KT"
    assert r["menu_items"] == ["제육볶음", "미역국", "배추김치"]
    assert r["source_image_path"] == str(image)
    assert "제육볶음" in result["answer"]


def test_query_menu_without_organization_returns_all_three(data_dir, vector_store):
    _write_sample_image(
        data_dir / "kt", "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치"
    )
    _write_sample_image(
        data_dir / "daesung", "daesung_menu", "2026-07-22 수요일 점심: 돈가스, 스프, 양배추샐러드"
    )
    _write_sample_image(
        data_dir / "kt_salad", "kt_salad_menu", "2026-07-22 수요일 점심: 닭가슴살샐러드, 고구마"
    )
    store = _build_store(data_dir)

    result = query_menu("오늘 식단 알려줘.", store=store, vector_store=vector_store, today=TODAY, now=NOW)

    assert result["success"] is True
    orgs = {r["organization"] for r in result["results"]}
    assert orgs == {"KT", "대성학원", "KT 샐러드"}


def test_query_menu_semantic_search_finds_menu_item(data_dir, vector_store):
    _write_sample_image(
        data_dir / "daesung",
        "daesung_menu",
        "\n".join(
            [
                "2026-07-20 월요일 점심: 비빔밥, 계란국",
                "2026-07-23 목요일 점심: 돈가스, 우동, 단무지",
            ]
        ),
    )
    store = _build_store(data_dir)
    store.load(vector_store=vector_store)  # 의미 검색용 인덱스도 만든다.

    result = query_menu(
        "이번 주에 돈가스 나오는 날이 언제야?",
        store=store,
        vector_store=vector_store,
        today=TODAY,
        now=NOW,
    )

    assert result["success"] is True
    assert any("돈가스" in r["menu_items"] for r in result["results"])


def test_query_menu_no_results_returns_failure_structure(data_dir, vector_store):
    store = _build_store(data_dir)
    result = query_menu("오늘 KT 메뉴 뭐야?", store=store, vector_store=vector_store, today=TODAY, now=NOW)

    assert result["success"] is False
    assert result["results"] == []
    assert result["answer"] == "해당 날짜에는 등록된 식단이 없습니다."


def test_query_menu_always_returns_same_shape_keys(data_dir, vector_store):
    store = _build_store(data_dir)
    result = query_menu("아무 의미 없는 질문", store=store, vector_store=vector_store, today=TODAY, now=NOW)
    assert set(result.keys()) == {"success", "query", "results", "answer"}


# ---------- 최종 정의서: 끼니 미지정 = 항상 점심, 업체 미지정 = 3개 업체 ----------


def test_query_menu_defaults_meal_type_to_lunch_regardless_of_time(data_dir, vector_store):
    _write_sample_image(
        data_dir / "kt", "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치"
    )
    store = _build_store(data_dir)

    for hour in (9, 15, 21):
        now = datetime(2026, 7, 22, hour, 0, tzinfo=KST)
        result = query_menu("오늘 KT 메뉴 뭐야?", store=store, vector_store=vector_store, today=TODAY, now=now)
        assert result["success"] is True, hour
        assert result["results"][0]["meal_type"] == "점심"


def test_query_menu_returns_salad_only_when_explicitly_requested(data_dir, vector_store):
    _write_sample_image(
        data_dir / "kt_salad", "salad_menu", "2026-07-22 수요일 점심: 닭가슴살샐러드, 고구마"
    )
    _write_sample_image(
        data_dir / "kt", "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치"
    )
    store = _build_store(data_dir)

    result = query_menu(
        "오늘 KT 샐러드 메뉴 알려줘.", store=store, vector_store=vector_store, today=TODAY, now=NOW
    )

    assert result["success"] is True
    assert len(result["results"]) == 1
    assert result["results"][0]["organization"] == "KT 샐러드"


def test_query_menu_does_not_fallback_to_other_date(data_dir, vector_store):
    # 7/23(내일) 메뉴만 있고 "오늘" 메뉴를 조회하면, 다른 날짜 메뉴로 대체되면 안 된다.
    _write_sample_image(
        data_dir / "kt", "kt_menu", "2026-07-23 목요일 점심: 돈까스, 우동, 단무지"
    )
    store = _build_store(data_dir)

    result = query_menu("오늘 KT 메뉴 뭐야?", store=store, vector_store=vector_store, today=TODAY, now=NOW)

    assert result["success"] is False
    assert result["results"] == []
    assert result["answer"] == "해당 날짜에는 등록된 식단이 없습니다."


# ---------- 끼니 동의어 ----------


def test_meal_type_synonyms_lunch_return_same_menu(data_dir, vector_store):
    _write_sample_image(
        data_dir / "kt", "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치"
    )
    store = _build_store(data_dir)

    for word in ["점심", "중식", "런치"]:
        result = query_menu(
            f"오늘 KT {word} 알려줘", store=store, vector_store=vector_store, today=TODAY, now=NOW
        )
        assert result["success"] is True, word
        assert result["results"][0]["meal_type"] == "점심"
        assert result["results"][0]["menu_items"] == ["제육볶음", "미역국", "배추김치"]


def test_meal_type_synonyms_dinner_return_same_menu(data_dir, vector_store):
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

    for word in ["저녁", "석식", "디너"]:
        result = query_menu(
            f"오늘 대성 {word} 알려줘", store=store, vector_store=vector_store, today=TODAY, now=NOW
        )
        assert result["success"] is True, word
        assert result["results"][0]["meal_type"] == "저녁"
        assert result["results"][0]["menu_items"] == ["삼겹살", "상추쌈"]


def test_daesung_lunch_and_dinner_are_distinguished(data_dir, vector_store):
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

    lunch_result = query_menu(
        "오늘 대성 점심 알려줘", store=store, vector_store=vector_store, today=TODAY, now=NOW
    )
    dinner_result = query_menu(
        "오늘 대성 저녁 알려줘", store=store, vector_store=vector_store, today=TODAY, now=NOW
    )

    assert lunch_result["results"][0]["menu_items"] == ["비빔밥", "계란국"]
    assert dinner_result["results"][0]["menu_items"] == ["삼겹살", "상추쌈"]


def test_kt_dinner_not_registered_returns_no_data_message(data_dir, vector_store):
    # KT는 저녁 데이터가 없으므로, 저녁을 직접 요청해도 임의로 다른 메뉴를 대신 반환하지 않는다.
    _write_sample_image(
        data_dir / "kt", "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치"
    )
    store = _build_store(data_dir)

    result = query_menu(
        "오늘 KT 저녁 알려줘", store=store, vector_store=vector_store, today=TODAY, now=NOW
    )

    assert result["success"] is False
    assert result["results"] == []
    assert result["answer"] == "해당 날짜에는 등록된 식단이 없습니다."
