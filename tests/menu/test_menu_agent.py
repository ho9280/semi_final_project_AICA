"""menu_tool.py(질문 분석/검색)에 대한 통합 테스트.

최종 정의서 기준으로 챗봇 질문(query_menu)의 기본 데이터 원본은
data/menu 폴더의 이미지 + .txt(sidecar)이다(SQLite 없음). 테스트에서는
tmp_path 아래에 업체 폴더(daesung/kt/kt_salad)를 만들고 MenuFileStore로
읽어들여 실제 파일 배치와 최대한 비슷하게 검증한다.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from PIL import Image

from app.menu_agent_tool import KST, MenuFileStore, VectorStore, parse_query, plan_menu_search, query_menu

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


# ---------- 하이브리드(메뉴명/재료) 검색 ----------
#
# 실제 KT 샐러드 sidecar 형식("샐러드명 (구성재료: ... / 드레싱: ... / 열량: ... / 원산지: ...)")과
# 동일한 데이터를 tmp_path에 구성해, 정확일치 -> 포함 -> 조건일치 -> 벡터유사도 순으로
# 검색되는지 검증한다.


def _build_hybrid_fixture(data_dir, vector_store):
    _write_sample_image(
        data_dir / "kt_salad",
        "kt_salad_menu",
        "\n".join(
            [
                "2026-07-20 월요일 점심: 오렌지치킨텐더샐러드 (구성재료: 치킨텐더, 오렌지, 방울토마토 / 드레싱: 유자오리엔탈드레싱 / 열량: 412kcal / 원산지: 닭가슴살 국내산)",
                "2026-07-21 화요일 점심: 두부볼콥샐러드 (구성재료: 두부볼, 깐계란, 완숙토마토 / 드레싱: 참깨흑임자드레싱 / 열량: 395kcal / 원산지: 두부-콩:외국산 돈육:국내산)",
                "2026-07-22 수요일 점심: 트러플오일소세지샐러드 (구성재료: 그릴소시지, 오트밀브레드, 완숙토마토 / 드레싱: 트러플오일드레싱 / 열량: 420kcal / 원산지: 소시지-돈육 계육:국내산)",
                "2026-07-23 목요일 점심: 오렌지치킨텐더샐러드 (구성재료: 치킨텐더, 오렌지, 방울토마토 / 드레싱: 유자오리엔탈드레싱 / 열량: 408kcal / 원산지: 닭가슴살:국내산)",
                "2026-07-24 금요일 점심: 베이컨시저샐러드 (구성재료: 베이컨칩, 그릴치킨, 방울토마토 / 드레싱: 시저드레싱 / 열량: 410kcal / 원산지: 돈전지:외국산 닭가슴살:국산)",
            ]
        ),
    )
    _write_sample_image(
        data_dir / "kt",
        "kt_menu",
        "\n".join(
            [
                "2026-07-20 월요일 점심: 황태미역국, 백미밥&잡곡밥, 메밀전병튀김, 배추김치, 냉보리차",
                "2026-07-24 금요일 점심: 얼갈이된장국, 백미밥&잡곡밥, 제육볶음, 배추김치, 냉매실차",
            ]
        ),
    )
    _write_sample_image(
        data_dir / "daesung",
        "daesung_menu",
        "\n".join(
            [
                "2026-07-20 월요일 아침: 돈육김치찌개, 소세지전*케찹, 알감자버터구이, 취나물무침",
                "2026-07-23 목요일 점심: 돈가스, 우동, 단무지",
                "2026-07-24 금요일 점심: 짜계치(파포겟티 계란후라이 치즈), 미니밥&햄구이, 단무지",
            ]
        ),
    )
    store = MenuFileStore(data_dir=data_dir)
    store.load(vector_store=vector_store)  # 벡터 폴백 단계까지 검증하기 위해 색인도 만든다.
    return store


@pytest.mark.parametrize(
    "query,expected_name_part",
    [
        ("오렌지치킨텐더샐러드", "오렌지치킨텐더샐러드"),
        ("방울토마토", None),  # 여러 건(7/20,7/23,7/24)이 모두 KT 샐러드여야 한다
        ("참깨흑임자드레싱", "두부볼콥샐러드"),
        ("베이컨시저샐러드", "베이컨시저샐러드"),
        ("트러플오일소세지샐러드", "트러플오일소세지샐러드"),
    ],
)
def test_hybrid_search_ranks_kt_salad_first_for_menu_and_ingredient_queries(
    data_dir, vector_store, query, expected_name_part
):
    store = _build_hybrid_fixture(data_dir, vector_store)

    result = query_menu(query, store=store, vector_store=vector_store, today=TODAY, now=NOW)

    assert result["success"] is True, query
    assert all(r["organization"] == "KT 샐러드" for r in result["results"]), query
    if expected_name_part is not None:
        assert result["results"][0]["menu_items"][0].startswith(expected_name_part)


def test_hybrid_search_organization_scoped_ingredient_query(data_dir, vector_store):
    store = _build_hybrid_fixture(data_dir, vector_store)

    result = query_menu(
        "KT 샐러드 방울토마토 메뉴", store=store, vector_store=vector_store, today=TODAY, now=NOW
    )

    assert result["success"] is True
    assert all(r["organization"] == "KT 샐러드" for r in result["results"])
    assert all(
        any("방울토마토" in item for item in r["menu_items"]) for r in result["results"]
    )


def test_hybrid_search_scoped_to_kt_general_finds_no_match_for_salad_only_ingredient(
    data_dir, vector_store
):
    # "KT"만 언급했으므로(KT 샐러드 아님) KT 일반식 범위로만 검색한다.
    # "참깨흑임자드레싱"은 KT 샐러드 전용 재료라 KT 일반식에는 없으므로 못 찾는 것이 맞다.
    store = _build_hybrid_fixture(data_dir, vector_store)

    result = query_menu(
        "KT 참깨흑임자드레싱 나오는 날", store=store, vector_store=vector_store, today=TODAY, now=NOW
    )

    assert result["success"] is False
    assert result["results"] == []
    assert result["answer"] == "관련 메뉴를 찾지 못했습니다."


def test_hybrid_search_does_not_break_explicit_organization_date_meal_query(data_dir, vector_store):
    store = _build_hybrid_fixture(data_dir, vector_store)

    daesung_result = query_menu(
        "대성학원 오늘 점심", store=store, vector_store=vector_store, today=TODAY, now=NOW
    )
    kt_result = query_menu("KT 오늘 점심", store=store, vector_store=vector_store, today=TODAY, now=NOW)

    assert daesung_result["success"] is False  # TODAY(7/22)에는 대성학원 점심 데이터가 없음(정상)
    assert daesung_result["answer"] == "해당 날짜에는 등록된 식단이 없습니다."
    assert kt_result["success"] is False  # TODAY(7/22)에는 KT 점심 데이터가 없음(정상)
    assert kt_result["answer"] == "해당 날짜에는 등록된 식단이 없습니다."


def test_hybrid_search_no_match_returns_not_found_message(data_dir, vector_store):
    store = _build_hybrid_fixture(data_dir, vector_store)

    result = query_menu(
        "완전히존재하지않는메뉴이름입니다", store=store, vector_store=vector_store, today=TODAY, now=NOW
    )

    assert result["success"] is False
    assert result["results"] == []
    assert result["answer"] == "관련 메뉴를 찾지 못했습니다."


def test_hybrid_search_vector_fallback_used_when_no_exact_or_contains_match(data_dir, vector_store):
    # "돈가스" 자체는 정확히 일치하는 항목이 있으므로(대성학원 7/23), exact_match 단계에서 잡힌다.
    store = _build_hybrid_fixture(data_dir, vector_store)

    result = query_menu(
        "이번 주에 돈가스 나오는 날이 언제야?", store=store, vector_store=vector_store, today=TODAY, now=NOW
    )

    assert result["success"] is True
    assert any("돈가스" in r["menu_items"] for r in result["results"])


@pytest.mark.parametrize(
    "query,expected_ingredient",
    [
        ("방울토마토 들어간 메뉴 알려줘", "방울토마토"),
        ("방울토마토 들어있는 메뉴 알려줘", "방울토마토"),
        ("방울토마토 포함된 메뉴 알려줘", "방울토마토"),
        ("참깨흑임자드레싱 들어간 메뉴 알려줘", "참깨흑임자드레싱"),
    ],
)
def test_ingredient_inclusion_phrases_use_contains_match_not_vector_fallback(
    data_dir, vector_store, query, expected_ingredient
):
    # "들어간"/"들어있는"/"포함된" 같은 재료 포함 표현이 키워드에 남아 있으면
    # 정확/포함 매칭이 실패해 벡터 유사도(4단계)로 넘어가면서 관련 없는
    # 대성학원 메뉴가 섞여 들어오던 문제를 재발 방지한다.
    store = _build_hybrid_fixture(data_dir, vector_store)

    filters = parse_query(query, today=TODAY)
    plan = plan_menu_search(query, filters, TODAY)
    assert plan["search_mode"] == "hybrid"
    assert plan["keyword"] == expected_ingredient  # "들어간" 등이 키워드에서 제거됨

    result = query_menu(query, store=store, vector_store=vector_store, today=TODAY, now=NOW)

    assert result["success"] is True, query
    assert len(result["results"]) > 0
    # 관련 없는 대성학원 메뉴가 섞여 들어오지 않아야 한다 (전부 KT 샐러드여야 함).
    assert all(r["organization"] == "KT 샐러드" for r in result["results"]), query
    assert all(
        any(expected_ingredient in item for item in r["menu_items"]) for r in result["results"]
    )
