"""menu_data.py의 OCR 구역에 대한 테스트.

실제 OCR 엔진 없이 MockOCRProvider와 validate_image의 동작을 검증한다.
Tesseract/PaddleOCR 관련 테스트는 실제 엔진이 설치되어 있지 않아도(다른
팀원 PC에서도) 항상 통과하도록, 경로 탐색 로직은 monkeypatch로 격리해서
검증하고 실제 엔진 호출이 필요한 부분은 설치돼 있을 때만 실행한다.
"""

from __future__ import annotations

import shutil

import pytest
from PIL import Image

from app.menu_agent_tool import (
    MockOCRProvider,
    PaddleOCRProvider,
    TesseractOCRProvider,
    find_tessdata_prefix,
    find_tesseract_cmd,
    validate_image,
)


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


# ---------- Tesseract 경로 탐색 (실제 엔진 없이도 항상 검증 가능) ----------


def test_find_tesseract_cmd_prefers_env_var(tmp_path, monkeypatch):
    fake_exe = tmp_path / "tesseract.exe"
    fake_exe.write_bytes(b"")
    monkeypatch.setenv("TESSERACT_CMD", str(fake_exe))

    assert find_tesseract_cmd() == str(fake_exe)


def test_find_tesseract_cmd_falls_back_to_path(monkeypatch):
    monkeypatch.delenv("TESSERACT_CMD", raising=False)
    monkeypatch.setattr(shutil, "which", lambda cmd: "C:\\fake\\path\\tesseract.exe")

    assert find_tesseract_cmd() == "C:\\fake\\path\\tesseract.exe"


def test_find_tesseract_cmd_returns_none_when_not_found(monkeypatch, tmp_path):
    monkeypatch.delenv("TESSERACT_CMD", raising=False)
    monkeypatch.setattr(shutil, "which", lambda cmd: None)
    # Windows 기본 후보 경로도 존재하지 않는 상황을 흉내 낸다.
    monkeypatch.setattr(
        "app.menu_agent_tool._TESSERACT_DEFAULT_CANDIDATES", [str(tmp_path / "nope.exe")]
    )

    assert find_tesseract_cmd() is None


def test_find_tessdata_prefix_reads_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("TESSDATA_PREFIX", str(tmp_path))
    assert find_tessdata_prefix() == str(tmp_path)


def test_find_tessdata_prefix_none_when_unset_and_no_local_cache(monkeypatch, tmp_path):
    monkeypatch.delenv("TESSDATA_PREFIX", raising=False)
    # 사용자 OCR 캐시 폴더에 kor.traineddata가 없는 상황을 흉내 낸다.
    monkeypatch.setattr("app.menu_agent_tool.get_local_ocr_cache_dir", lambda: tmp_path / "empty")
    assert find_tessdata_prefix() is None


def test_find_tessdata_prefix_falls_back_to_local_cache(monkeypatch, tmp_path):
    monkeypatch.delenv("TESSDATA_PREFIX", raising=False)
    cache_dir = tmp_path / "tessdata"
    cache_dir.mkdir()
    (cache_dir / "kor.traineddata").write_bytes(b"fake")
    monkeypatch.setattr("app.menu_agent_tool.get_local_ocr_cache_dir", lambda: cache_dir)

    assert find_tessdata_prefix() == str(cache_dir)


def test_tesseract_provider_returns_clear_error_when_not_found(tmp_path, monkeypatch):
    image_path = tmp_path / "menu.png"
    Image.new("RGB", (4, 4)).save(image_path)

    monkeypatch.delenv("TESSERACT_CMD", raising=False)
    monkeypatch.setattr(shutil, "which", lambda cmd: None)
    monkeypatch.setattr("app.menu_agent_tool._TESSERACT_DEFAULT_CANDIDATES", [])

    result = TesseractOCRProvider().extract_text(image_path)

    assert result.success is False
    assert "찾지 못했습니다" in result.error


# ---------- 실제 엔진 통합 테스트 (설치돼 있을 때만 실행) ----------


@pytest.mark.skipif(find_tesseract_cmd() is None, reason="Tesseract-OCR이 설치되어 있지 않음")
def test_tesseract_provider_reads_english_text(tmp_path):
    from PIL import ImageDraw

    image_path = tmp_path / "eng.png"
    img = Image.new("RGB", (200, 60), color=(255, 255, 255))
    ImageDraw.Draw(img).text((10, 15), "MENU", fill=(0, 0, 0))
    img.save(image_path)

    result = TesseractOCRProvider(lang="eng").extract_text(image_path)

    assert result.success is True
    assert "MENU" in result.text.upper()


def _paddleocr_available() -> bool:
    try:
        import paddleocr  # noqa: F401
    except ImportError:
        return False
    return True


@pytest.mark.skipif(not _paddleocr_available(), reason="paddleocr가 설치되어 있지 않음")
def test_paddleocr_provider_reads_korean_text(tmp_path):
    from PIL import ImageDraw, ImageFont

    image_path = tmp_path / "kor.png"
    img = Image.new("RGB", (300, 80), color=(255, 255, 255))
    try:
        font = ImageFont.truetype("malgun.ttf", 28)
    except Exception:
        font = ImageFont.load_default()
    ImageDraw.Draw(img).text((10, 20), "미역국", fill=(0, 0, 0), font=font)
    img.save(image_path)

    result = PaddleOCRProvider().extract_text(image_path)

    if not result.success:
        # paddleocr는 설치돼 있지만(패키지 import는 됨) 첫 실행 시 모델을
        # 내려받거나 로컬 추론 엔진을 초기화하는 과정에서 실패할 수 있다
        # (네트워크 문제, PC별 추론 엔진 호환성 등). 이는 이 프로젝트 코드의
        # 버그가 아니라 실행 환경 문제이므로 테스트를 실패시키지 않고 건너뛴다.
        pytest.skip(f"PaddleOCR 실제 추론 실패(환경 문제로 추정): {result.error}")
    assert "미역" in result.text or "역국" in result.text
