"""menu_agent.py에 대한 통합 테스트.

OCR은 MockOCRProvider(sidecar .txt 파일)를 사용하므로 실제 OCR 엔진 없이도
전체 흐름(이미지 등록 -> 저장 -> 질문 -> 답변)을 검증할 수 있다.
"""

from __future__ import annotations

from datetime import date

import pytest
from PIL import Image

from app.menu.menu_agent import parse_query, query_menu, register_menu_image
from app.menu.menu_embedding import VectorStore
from app.menu.menu_repository import MenuRepository

TODAY = date(2026, 7, 22)  # 수요일


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

    result = query_menu("오늘 KT 메뉴 뭐야?", repository=repo, vector_store=vector_store, today=TODAY)

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

    result = query_menu("오늘 식단 알려줘.", repository=repo, vector_store=vector_store, today=TODAY)

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
    result = query_menu("오늘 KT 메뉴 뭐야?", repository=repo, vector_store=vector_store, today=TODAY)

    assert result["success"] is False
    assert result["results"] == []
    assert "등록되어 있지 않습니다" in result["answer"]


def test_query_menu_always_returns_same_shape_keys(tmp_path, repo, vector_store):
    result = query_menu("아무 의미 없는 질문", repository=repo, vector_store=vector_store, today=TODAY)
    assert set(result.keys()) == {"success", "query", "results", "answer"}
