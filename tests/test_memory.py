from __future__ import annotations

from app.memory.fakes import InMemoryEpisodicStore, InMemorySemanticStore
from app.memory.manager import MemoryManager


def test_episodic_store_appends_and_orders_history():
    store = InMemoryEpisodicStore()
    store.append_turn("s1", "user", "hello")
    store.append_turn("s1", "assistant", "hi there")
    history = store.get_history("s1")
    assert [h["role"] for h in history] == ["user", "assistant"]
    assert history[0]["content"] == "hello"


def test_episodic_store_respects_limit():
    store = InMemoryEpisodicStore()
    for i in range(10):
        store.append_turn("s1", "user", f"msg {i}")
    history = store.get_history("s1", limit=3)
    assert len(history) == 3
    assert history[-1]["content"] == "msg 9"


def test_episodic_store_isolates_sessions():
    store = InMemoryEpisodicStore()
    store.append_turn("s1", "user", "hello")
    store.append_turn("s2", "user", "goodbye")
    assert len(store.get_history("s1")) == 1
    assert len(store.get_history("s2")) == 1


def test_semantic_store_search_ranks_by_term_overlap():
    store = InMemorySemanticStore()
    store.add_memory("s1", "DataSphere 1 raised prices for enterprise customers")
    store.add_memory("s1", "The weather was sunny in Berlin")
    results = store.search("DataSphere enterprise pricing")
    assert results
    assert "DataSphere" in results[0]["content"]


def test_memory_manager_records_turn_and_recalls_history():
    manager = MemoryManager(InMemoryEpisodicStore(), InMemorySemanticStore())
    manager.record_turn("s1", "user", "What is DataSphere's market share?")
    manager.record_turn("s1", "assistant", "DataSphere holds roughly 6.9% market share.")

    history = manager.recall_history("s1")
    assert len(history) == 2

    semantic_hits = manager.recall_semantic("DataSphere market share")
    assert semantic_hits
    assert "DataSphere" in semantic_hits[0]["content"]
