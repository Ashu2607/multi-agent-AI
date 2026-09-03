from __future__ import annotations

from tests.conftest import FakeChatModel, FakeMessage

import app.tools.text_to_sql as text_to_sql


def test_run_text_to_sql_executes_valid_generated_query(monkeypatch):
    monkeypatch.setattr(
        text_to_sql, "generate_sql", lambda question: "SELECT company_name FROM competitors LIMIT 5"
    )
    result = text_to_sql.run_text_to_sql("List some competitors")
    assert result.error is None
    assert result.columns == ["company_name"]
    assert result.row_count > 0


def test_run_text_to_sql_repairs_invalid_query_once(monkeypatch):
    monkeypatch.setattr(text_to_sql, "generate_sql", lambda question: "DROP TABLE competitors")
    fake_llm = FakeChatModel(raw_responses=[FakeMessage("SELECT company_name FROM competitors")])
    monkeypatch.setattr(text_to_sql, "_get_llm", lambda: fake_llm)

    result = text_to_sql.run_text_to_sql("List competitors")
    assert result.error is None
    assert result.row_count > 0


def test_run_text_to_sql_gives_up_after_failed_repair(monkeypatch):
    monkeypatch.setattr(text_to_sql, "generate_sql", lambda question: "DROP TABLE competitors")
    fake_llm = FakeChatModel(raw_responses=[FakeMessage("DELETE FROM competitors")])
    monkeypatch.setattr(text_to_sql, "_get_llm", lambda: fake_llm)

    result = text_to_sql.run_text_to_sql("List competitors")
    assert result.error is not None
    assert result.row_count == 0


def test_strip_fences_removes_markdown_code_block():
    raw = "```sql\nSELECT 1\n```"
    assert text_to_sql._strip_fences(raw) == "SELECT 1"
