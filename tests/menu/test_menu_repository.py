"""menu_repository.py에 대한 테스트."""

from __future__ import annotations

import pytest

from app.menu.menu_repository import MenuRepository, make_entry_id


@pytest.fixture
def repo(tmp_path):
    return MenuRepository(db_path=tmp_path / "menu.db")


def _sample_entry(**overrides) -> dict:
    entry = {
        "organization": "KT",
        "menu_type": "general",
        "menu_date": "2026-07-22",
        "weekday": "수요일",
        "meal_type": "점심",
        "menu_items": ["제육볶음", "미역국", "배추김치"],
        "source_image_path": "data/menu/kt/kt_2026-07-20.png",
        "ocr_raw_text": "2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치",
    }
    entry.update(overrides)
    return entry


def test_upsert_and_get_by_id(repo):
    entry_id = repo.upsert_menu_entry(_sample_entry())

    assert entry_id == make_entry_id("KT", "general", "2026-07-22", "점심")

    stored = repo.get_by_id(entry_id)
    assert stored is not None
    assert stored["organization"] == "KT"
    assert stored["menu_items"] == ["제육볶음", "미역국", "배추김치"]
    assert stored["source_image_path"] == "data/menu/kt/kt_2026-07-20.png"


def test_duplicate_upsert_does_not_create_new_row(repo):
    repo.upsert_menu_entry(_sample_entry())
    repo.upsert_menu_entry(_sample_entry(menu_items=["새로운메뉴"]))

    assert repo.count() == 1
    stored = repo.get_by_id(make_entry_id("KT", "general", "2026-07-22", "점심"))
    assert stored["menu_items"] == ["새로운메뉴"]


def test_get_by_condition_filters_by_organization_and_date(repo):
    repo.upsert_menu_entry(_sample_entry())
    repo.upsert_menu_entry(
        _sample_entry(organization="대성학원", menu_date="2026-07-22", source_image_path="x.png")
    )
    repo.upsert_menu_entry(_sample_entry(menu_date="2026-07-23", weekday="목요일"))

    kt_results = repo.get_by_condition(organization="KT")
    assert len(kt_results) == 2
    assert all(r["organization"] == "KT" for r in kt_results)

    today_kt = repo.get_by_condition(organization="KT", menu_date="2026-07-22")
    assert len(today_kt) == 1
    assert today_kt[0]["menu_date"] == "2026-07-22"


def test_get_by_condition_no_match_returns_empty_list(repo):
    repo.upsert_menu_entry(_sample_entry())
    results = repo.get_by_condition(organization="KT", menu_date="2099-01-01")
    assert results == []


def test_get_by_condition_by_weekday(repo):
    repo.upsert_menu_entry(_sample_entry())
    results = repo.get_by_condition(weekday="수요일")
    assert len(results) == 1
    assert results[0]["weekday"] == "수요일"


def test_persistence_across_repository_instances(tmp_path):
    db_path = tmp_path / "menu.db"
    repo1 = MenuRepository(db_path=db_path)
    repo1.upsert_menu_entry(_sample_entry())

    repo2 = MenuRepository(db_path=db_path)
    assert repo2.count() == 1
