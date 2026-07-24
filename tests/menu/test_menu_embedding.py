"""menu_data.py의 임베딩/벡터 검색 구역에 대한 테스트."""

from __future__ import annotations

import pytest

from app.menu_agent_tool import VectorStore, embed_text


@pytest.fixture
def store(tmp_path):
    return VectorStore(store_path=tmp_path / "vector_store.json")


def test_embed_text_is_deterministic():
    v1 = embed_text("제육볶음 미역국 배추김치")
    v2 = embed_text("제육볶음 미역국 배추김치")
    assert v1 == v2


def test_embed_text_different_text_differs():
    v1 = embed_text("제육볶음 미역국")
    v2 = embed_text("돈까스 우동")
    assert v1 != v2


def test_upsert_and_search_finds_relevant_document(store):
    store.upsert("kt_2026-07-22_점심", "KT 일반 2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치")
    store.upsert("daesung_2026-07-22_점심", "대성학원 2026-07-22 수요일 점심: 돈까스, 우동, 단무지")

    results = store.search("돈까스 나오는 날", top_k=1)

    assert len(results) == 1
    assert results[0]["id"] == "daesung_2026-07-22_점심"


def test_search_with_metadata_filter(store):
    store.upsert(
        "kt_2026-07-22_점심",
        "KT 일반 2026-07-22 수요일 점심: 돈까스, 우동",
        metadata={"organization": "KT"},
    )
    store.upsert(
        "daesung_2026-07-22_점심",
        "대성학원 2026-07-22 수요일 점심: 돈까스, 김치찌개",
        metadata={"organization": "대성학원"},
    )

    results = store.search("돈까스", top_k=5, metadata_filter={"organization": "KT"})

    assert len(results) == 1
    assert results[0]["metadata"]["organization"] == "KT"


def test_upsert_duplicate_id_overwrites_not_duplicates(store):
    store.upsert("id1", "제육볶음 미역국")
    store.upsert("id1", "돈까스 우동")

    assert store.count() == 1
    results = store.search("돈까스", top_k=1)
    assert results[0]["document"] == "돈까스 우동"


def test_search_empty_store_returns_empty_list(store):
    assert store.search("아무 메뉴") == []


def test_persistence_across_instances(tmp_path):
    store_path = tmp_path / "vector_store.json"
    store1 = VectorStore(store_path=store_path)
    store1.upsert("id1", "제육볶음 미역국")

    store2 = VectorStore(store_path=store_path)
    assert store2.count() == 1
    results = store2.search("제육볶음")
    assert results[0]["id"] == "id1"
