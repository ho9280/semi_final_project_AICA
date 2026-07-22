"""menu_ocr.py에 대한 테스트.

실제 OCR 엔진 없이 MockOCRProvider와 validate_image의 동작을 검증한다.
"""

from __future__ import annotations

from PIL import Image

from app.menu.menu_ocr import MockOCRProvider, validate_image


def _make_png(path, size=(4, 4)) -> None:
    Image.new("RGB", size, color=(255, 255, 255)).save(path)


def test_validate_image_missing_file(tmp_path):
    missing = tmp_path / "not_exist.png"
    assert validate_image(missing) == "이미지 없음"


def test_validate_image_unsupported_extension(tmp_path):
    path = tmp_path / "menu.gif"
    path.write_bytes(b"not really a gif")
    assert validate_image(path) == "지원하지 않는 확장자"


def test_validate_image_corrupted_file(tmp_path):
    path = tmp_path / "broken.png"
    path.write_bytes(b"this is not a valid png file")
    assert validate_image(path) == "손상된 이미지"


def test_validate_image_ok(tmp_path):
    path = tmp_path / "good.png"
    _make_png(path)
    assert validate_image(path) is None


def test_mock_ocr_success_reads_sidecar_text(tmp_path):
    image_path = tmp_path / "kt_2026-07-22.png"
    _make_png(image_path)
    sidecar = tmp_path / "kt_2026-07-22.txt"
    sidecar.write_text(
        "2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치", encoding="utf-8"
    )

    result = MockOCRProvider().extract_text(image_path)

    assert result.success is True
    assert result.error is None
    assert "제육볶음" in result.text
    assert result.image_path == str(image_path)


def test_mock_ocr_missing_sidecar_returns_no_result_error(tmp_path):
    image_path = tmp_path / "no_sidecar.png"
    _make_png(image_path)

    result = MockOCRProvider().extract_text(image_path)

    assert result.success is False
    assert result.error == "OCR 결과 없음"
    assert result.text is None


def test_mock_ocr_empty_sidecar_returns_no_result_error(tmp_path):
    image_path = tmp_path / "empty_sidecar.png"
    _make_png(image_path)
    (tmp_path / "empty_sidecar.txt").write_text("   \n  ", encoding="utf-8")

    result = MockOCRProvider().extract_text(image_path)

    assert result.success is False
    assert result.error == "OCR 결과 없음"


def test_mock_ocr_missing_image_returns_error(tmp_path):
    image_path = tmp_path / "missing.png"

    result = MockOCRProvider().extract_text(image_path)

    assert result.success is False
    assert result.error == "이미지 없음"


def test_mock_ocr_unsupported_extension_returns_error(tmp_path):
    image_path = tmp_path / "menu.bmp"
    image_path.write_bytes(b"fake bmp content")

    result = MockOCRProvider().extract_text(image_path)

    assert result.success is False
    assert result.error == "지원하지 않는 확장자"


def test_mock_ocr_corrupted_image_returns_error(tmp_path):
    image_path = tmp_path / "corrupted.jpg"
    image_path.write_bytes(b"not a real jpg")

    result = MockOCRProvider().extract_text(image_path)

    assert result.success is False
    assert result.error == "손상된 이미지"
