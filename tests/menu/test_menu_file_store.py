"""menu_data.py의 파일 기반 저장소(MenuFileStore) 구역에 대한 테스트.

MenuFileStore는 data/menu 폴더 구조(업체별 하위 폴더 + 이미지/텍스트)를 그대로
흉내 낸 tmp_path 아래에서 스캔 동작을 검증한다.
"""

from __future__ import annotations

import pytest
from PIL import Image

from app.menu_agent_tool import MenuFileStore


def _write_image(folder, filename: str, ocr_text: str | None = None):
    folder.mkdir(parents=True, exist_ok=True)
    image_path = folder / f"{filename}.png"
    Image.new("RGB", (4, 4), color=(255, 255, 255)).save(image_path)
    if ocr_text is not None:
        (folder / f"{filename}.txt").write_text(ocr_text, encoding="utf-8")
    return image_path


def test_load_reads_entries_from_org_folders(tmp_path):
    _write_image(tmp_path / "kt", "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국")
    store = MenuFileStore(data_dir=tmp_path)

    result = store.load()

    assert result.entry_count == 1
    assert result.errors == []
    entries = store.get_by_condition(organization="KT")
    assert entries[0]["menu_items"] == ["제육볶음", "미역국"]


def test_load_ignores_non_image_files(tmp_path):
    org_dir = tmp_path / "kt"
    _write_image(org_dir, "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국")
    (org_dir / "readme.md").write_text("이미지가 아닌 파일", encoding="utf-8")
    store = MenuFileStore(data_dir=tmp_path)

    result = store.load()

    assert result.entry_count == 1
    assert result.errors == []


def test_load_missing_sidecar_is_reported_as_error_without_stopping_scan(tmp_path):
    _write_image(tmp_path / "kt", "kt_no_sidecar")  # .txt 없음
    _write_image(tmp_path / "daesung", "daesung_menu", "2026-07-22 수요일 점심: 비빔밥, 계란국")
    store = MenuFileStore(data_dir=tmp_path)

    result = store.load()

    assert result.entry_count == 1  # daesung 항목은 정상 반영
    assert len(result.errors) == 1
    assert result.errors[0].error == "OCR 결과 없음"
    assert "kt_no_sidecar" in result.errors[0].image_path


def test_load_unparseable_sidecar_is_reported_as_error(tmp_path):
    _write_image(tmp_path / "kt", "kt_menu", "형식에 맞지 않는 아무 텍스트")
    store = MenuFileStore(data_dir=tmp_path)

    result = store.load()

    assert result.entry_count == 0
    assert len(result.errors) == 1
    assert result.errors[0].error == "메뉴 구조화 실패"


def test_reload_does_not_duplicate_same_entry(tmp_path):
    _write_image(tmp_path / "kt", "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국")
    store = MenuFileStore(data_dir=tmp_path)

    first = store.load()
    second = store.load()

    assert first.entry_count == 1
    assert second.entry_count == 1  # 다시 스캔해도 중복으로 쌓이지 않는다


def test_two_images_with_same_condition_deduplicate_by_last_loaded(tmp_path):
    # 파일명이 다르더라도 (업체,종류,날짜,끼니) 조합이 같으면 하나로 합쳐진다.
    _write_image(tmp_path / "kt", "a_kt_menu", "2026-07-22 수요일 점심: 첫번째메뉴")
    _write_image(tmp_path / "kt", "b_kt_menu", "2026-07-22 수요일 점심: 두번째메뉴")
    store = MenuFileStore(data_dir=tmp_path)

    result = store.load()

    assert result.entry_count == 1  # 정렬 순서상 나중 파일(b_kt_menu)이 우선한다
    entries = store.get_by_condition(organization="KT")
    assert entries[0]["menu_items"] == ["두번째메뉴"]


def test_get_by_condition_filters(tmp_path):
    _write_image(tmp_path / "kt", "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국")
    _write_image(tmp_path / "daesung", "daesung_menu", "2026-07-22 수요일 점심: 비빔밥, 계란국")
    store = MenuFileStore(data_dir=tmp_path)
    store.load()

    assert len(store.get_by_condition(organization="KT")) == 1
    assert len(store.get_by_condition(menu_date="2026-07-22")) == 2
    assert store.get_by_condition(organization="KT", menu_date="2099-01-01") == []


def test_missing_organization_folder_is_skipped_without_error(tmp_path):
    # kt/daesung/kt_salad 폴더 중 아무것도 만들지 않아도 예외 없이 빈 결과를 반환한다.
    store = MenuFileStore(data_dir=tmp_path)
    result = store.load()
    assert result.entry_count == 0
    assert result.errors == []


def test_load_does_not_create_sqlite_db(tmp_path):
    _write_image(tmp_path / "kt", "kt_menu", "2026-07-22 수요일 점심: 제육볶음, 미역국")
    store = MenuFileStore(data_dir=tmp_path)
    store.load()

    db_files = list(tmp_path.rglob("*.db"))
    assert db_files == []
