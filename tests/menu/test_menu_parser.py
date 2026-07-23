"""menu_parser.py에 대한 테스트."""

from __future__ import annotations

from app.menu.menu_parser import parse_ocr_text


def test_parse_single_line():
    raw_text = "2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치"
    result = parse_ocr_text(raw_text, organization="KT", menu_type="general", source_image_path="a.png")

    assert result.success is True
    assert len(result.entries) == 1

    entry = result.entries[0]
    assert entry["organization"] == "KT"
    assert entry["menu_type"] == "general"
    assert entry["menu_date"] == "2026-07-22"
    assert entry["weekday"] == "수요일"
    assert entry["meal_type"] == "점심"
    assert entry["menu_items"] == ["제육볶음", "미역국", "배추김치"]
    assert entry["source_image_path"] == "a.png"
    assert entry["ocr_raw_text"] == raw_text


def test_parse_multiple_lines():
    raw_text = "\n".join(
        [
            "2026-07-20 월요일 점심: 김치찌개, 계란말이",
            "2026-07-21 화요일 점심: 된장찌개, 잡채",
            "2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치",
        ]
    )
    result = parse_ocr_text(raw_text, organization="대성학원", menu_type="general", source_image_path="b.png")

    assert result.success is True
    assert len(result.entries) == 3
    assert [e["menu_date"] for e in result.entries] == ["2026-07-20", "2026-07-21", "2026-07-22"]


def test_parse_ignores_unmatched_lines():
    raw_text = "\n".join(
        [
            "이번 주 식단표",
            "2026-07-22 수요일 점심: 제육볶음, 미역국",
            "",
            "문의: 02-1234-5678",
        ]
    )
    result = parse_ocr_text(raw_text, organization="KT", menu_type="general", source_image_path="c.png")

    assert result.success is True
    assert len(result.entries) == 1


def test_parse_empty_text_returns_error():
    result = parse_ocr_text("", organization="KT", menu_type="general", source_image_path="d.png")
    assert result.success is False
    assert result.error == "OCR 결과 없음"
    assert result.entries == []


def test_parse_no_matching_lines_returns_structuring_error():
    raw_text = "완전히 형식에 맞지 않는 텍스트\n또 다른 줄"
    result = parse_ocr_text(raw_text, organization="KT", menu_type="general", source_image_path="e.png")
    assert result.success is False
    assert result.error == "메뉴 구조화 실패"


def test_parse_various_separators():
    raw_text = "2026-07-23 목요일 저녁: 돈까스/양배추샐러드·단무지, 우동"
    result = parse_ocr_text(raw_text, organization="KT 샐러드", menu_type="salad", source_image_path="f.png")

    assert result.success is True
    assert result.entries[0]["menu_items"] == ["돈까스", "양배추샐러드", "단무지", "우동"]


def test_parse_invalid_weekday_line_is_ignored():
    raw_text = "2026-07-22 수욜: 제육볶음"  # "수욜"은 WEEKDAYS에 없는 잘못된 표기
    result = parse_ocr_text(raw_text, organization="KT", menu_type="general", source_image_path="g.png")
    assert result.success is False
    assert result.error == "메뉴 구조화 실패"
