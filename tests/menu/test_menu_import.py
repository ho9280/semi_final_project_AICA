"""app.menu_agent_tool의 OCR 자동 등록 파이프라인(preview_menu_ocr,
infer_menu_fields, import_menu_image)에 대한 테스트.

실제 OCR 엔진(Tesseract/PaddleOCR) 설치 여부와 무관하게 항상 통과해야 하는
"안전장치" 테스트(기존 TXT 보호, 중복 이미지 방지, 잘못된 이미지 처리)와,
엔진이 실제로 있을 때만 실행되는 종단 간(end-to-end) 테스트를 분리한다.

모든 테스트는 tmp_path 아래에 격리된 데이터를 만들어 쓰므로, 실제
data/menu의 검수된 이미지·TXT나 vector_store.json/menu.db를 전혀 건드리지
않는다.
"""

from __future__ import annotations

import json

import pytest
from PIL import Image

from app.menu_agent_tool import (
    MenuFileStore,
    find_tesseract_cmd,
    import_menu_image,
    infer_menu_fields,
    preview_menu_ocr,
)


def _write_png(path, size=(300, 100)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color=(255, 255, 255)).save(path)


# ---------- 안전장치 (엔진 설치 여부와 무관하게 항상 통과) ----------


def test_preview_menu_ocr_missing_image_returns_structured_error():
    result = preview_menu_ocr("존재하지-않는-파일.png")
    assert result["success"] is False
    assert result["error"] == "이미지 없음"
    assert result["preview_path"] is None


def test_import_menu_image_missing_image_is_rejected():
    result = import_menu_image("존재하지-않는-파일.png")
    assert result["success"] is False
    assert result["status"] == "rejected"
    assert result["failed_stage"] == "image_validation"
    assert result["data_changed"] is False


def test_import_menu_image_refuses_to_overwrite_existing_txt(tmp_path):
    kt_dir = tmp_path / "kt"
    image_path = kt_dir / "already_registered.png"
    _write_png(image_path)
    sidecar = image_path.with_suffix(".txt")
    original_content = "2026-07-20 월요일 점심: 원본메뉴\n"
    sidecar.write_text(original_content, encoding="utf-8")

    store = MenuFileStore(data_dir=tmp_path)
    store.load()

    result = import_menu_image(image_path, store=store)

    assert result["success"] is False
    assert result["status"] == "rejected"
    assert result["failed_stage"] == "existing_txt_protection"
    assert result["data_changed"] is False
    # 정식 sidecar TXT는 손대지 않아야 한다.
    assert sidecar.read_text(encoding="utf-8") == original_content


def test_infer_menu_fields_unknown_organization_folder_fails_cleanly(tmp_path):
    image_path = tmp_path / "unknown_org" / "menu.png"
    _write_png(image_path)

    result = infer_menu_fields(image_path)

    assert result["success"] is False
    assert result["organization_code"] is None
    assert "업체를 판별하지 못했습니다" in result["error"]


def test_import_menu_image_never_crashes_on_unexpected_error(tmp_path, monkeypatch):
    kt_dir = tmp_path / "kt"
    image_path = kt_dir / "menu.png"
    _write_png(image_path)

    def _boom(*args, **kwargs):
        raise RuntimeError("주입된 오류")

    monkeypatch.setattr("app.menu_agent_tool.infer_menu_fields", _boom)

    result = import_menu_image(image_path)

    assert result["success"] is False
    assert result["status"] == "rejected"
    assert result["data_changed"] is False
    assert "예상치 못한 오류" in result["error"]


# ---------- 실제 엔진 종단 간 테스트 (설치돼 있을 때만 실행) ----------


@pytest.mark.skipif(find_tesseract_cmd() is None, reason="Tesseract-OCR이 설치되어 있지 않음")
def test_import_menu_image_end_to_end_with_real_engine(tmp_path):
    from PIL import ImageDraw, ImageFont

    kt_dir = tmp_path / "kt"
    image_path = kt_dir / "new_menu.png"
    kt_dir.mkdir(parents=True)

    img = Image.new("RGB", (700, 260), color=(255, 255, 255))
    try:
        font = ImageFont.truetype("malgun.ttf", 36)
    except Exception:
        font = ImageFont.load_default()
    d = ImageDraw.Draw(img)
    d.text((30, 20), "7.22 수요일", fill=(0, 0, 0), font=font)
    d.text((30, 100), "테스트메뉴", fill=(0, 0, 0), font=font)
    img.save(image_path)

    store = MenuFileStore(data_dir=tmp_path)
    store.load()

    result = import_menu_image(image_path, store=store)

    # OCR 품질에 따라 성공/거부 둘 다 나올 수 있지만(신뢰도 낮으면 정상적으로
    # 거부해야 함), 어느 쪽이든 스키마와 데이터 보호 원칙은 항상 지켜야 한다.
    assert result["success"] in (True, False)
    if result["success"]:
        assert result["status"] in ("imported", "imported_with_inference")
        assert result["reloaded"] is True
        txt_path = image_path.with_suffix(".txt")
        assert txt_path.exists()
        # 생성된 TXT가 실제로 파서를 통과하는 형식인지 재확인한다.
        from app.menu_agent_tool import parse_ocr_text

        parsed = parse_ocr_text(
            txt_path.read_text(encoding="utf-8"), organization="KT", menu_type="general", source_image_path=str(image_path)
        )
        assert parsed.success is True
    else:
        assert result["status"] == "rejected"
        assert result["data_changed"] is False
        # 실패했다면 정식 TXT를 만들지 않았어야 한다.
        assert not image_path.with_suffix(".txt").exists()
