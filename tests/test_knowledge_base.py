from __future__ import annotations

from app.tools import knowledge_base


def test_search_returns_empty_when_store_not_built(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge_base, "CHROMA_DIR", tmp_path / "does-not-exist")
    results = knowledge_base.search_knowledge_base("compliance policy")
    assert results == []


def test_knowledge_base_search_tool_reports_missing_store(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge_base, "CHROMA_DIR", tmp_path / "does-not-exist")
    output = knowledge_base.knowledge_base_search_tool.invoke({"query": "compliance policy"})
    assert "No knowledge base results" in output
