from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Force the in-memory memory backend and dummy API keys so the suite never
# needs live Redis/Zep/OpenAI network access. Must be set before app.config
# is imported anywhere (fixtures below import lazily to respect this).
os.environ.setdefault("MEMORY_BACKEND", "local")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("TAVILY_API_KEY", "test-key")
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")

import pytest  # noqa: E402


class FakeStructuredLLM:
    """Stands in for `ChatOpenAI(...).with_structured_output(Model)`."""

    def __init__(self, responses):
        self._responses = list(responses)

    def invoke(self, _messages):
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


class FakeChatModel:
    """Stands in for ChatOpenAI itself, for both structured and raw .invoke() use."""

    def __init__(self, structured_responses=None, raw_responses=None):
        self._structured_responses = structured_responses or []
        self._raw_responses = list(raw_responses or [])
        self._structured_llm = None

    def with_structured_output(self, _schema):
        # Memoized: the graph calls .with_structured_output(...) fresh on
        # every node visit, but the response queue must persist across those
        # calls (each visit should consume the next queued response).
        if self._structured_llm is None:
            self._structured_llm = FakeStructuredLLM(self._structured_responses)
        return self._structured_llm

    def invoke(self, _messages):
        if len(self._raw_responses) > 1:
            return self._raw_responses.pop(0)
        return self._raw_responses[0]


class FakeMessage:
    def __init__(self, content: str):
        self.content = content


@pytest.fixture(autouse=True)
def _isolate_approvals_db(tmp_path, monkeypatch):
    """Every test gets its own approvals.db so tests don't leak state."""
    import app.config as config
    import app.tools.approval_store as approval_store

    db_path = tmp_path / "approvals.db"
    monkeypatch.setattr(config, "APPROVALS_DB_PATH", db_path)
    monkeypatch.setattr(approval_store, "APPROVALS_DB_PATH", db_path)
    yield


@pytest.fixture
def fake_message():
    return FakeMessage


@pytest.fixture(scope="session", autouse=True)
def _ensure_structured_data():
    """market_news/pricing_comparison tables are added by scripts/ingest_structured_data.py;
    make sure they exist before any SQL test runs, regardless of setup order."""
    import sqlite3

    from app.config import SALES_DB_PATH

    con = sqlite3.connect(SALES_DB_PATH)
    try:
        tables = {
            row[0]
            for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    finally:
        con.close()

    if not {"market_news", "pricing_comparison"} <= tables:
        from scripts.ingest_structured_data import main as ingest_main

        ingest_main()
