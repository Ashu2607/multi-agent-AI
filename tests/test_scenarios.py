"""20 synthetic end-to-end scenarios (milestone requirement: "at least 20
synthetic test scenarios" demonstrating routing accuracy, memory recall
performance, SQL validation, and report generation). Each scenario is a
short, independent, offline-runnable check.
"""
from __future__ import annotations

import pytest

from app.memory.fakes import InMemoryEpisodicStore, InMemorySemanticStore
from app.memory.manager import MemoryManager
from app.schemas import ReportDraft, ReportSection, RouteDecision, RouteTarget
from app.tools import approval_store
from app.tools.report_writer import contains_sensitive_data, finalize_draft
from app.tools.sql_validation import validate_sql
from tests.conftest import FakeChatModel

import app.agents.supervisor as supervisor_mod


def _draft(summary="ok", content="body"):
    return ReportDraft(title="R", executive_summary=summary, sections=[ReportSection(heading="h", content=content)])


# --- SQL validation scenarios (1-6) ---------------------------------------

@pytest.mark.parametrize(
    "scenario_id,sql,expect_valid",
    [
        ("sql-01-simple-select", "SELECT company_name FROM competitors", True),
        ("sql-02-aggregate", "SELECT AVG(market_share) FROM competitors", True),
        ("sql-03-join", "SELECT * FROM products p JOIN competitors c ON p.competitor_id = c.competitor_id", True),
        ("sql-04-drop-blocked", "DROP TABLE quarterly_sales", False),
        ("sql-05-stacked-statements-blocked", "SELECT * FROM competitors; DELETE FROM competitors;", False),
        ("sql-06-unlisted-table-blocked", "SELECT * FROM users", False),
    ],
)
def test_sql_validation_scenario(scenario_id, sql, expect_valid):
    result = validate_sql(sql)
    assert result.is_valid is expect_valid, scenario_id


# --- Supervisor routing scenarios (7-11) ----------------------------------

def _state(**overrides):
    state = {"session_id": "s", "task": "t", "findings": [], "iterations": 0, "draft": None, "approval": None}
    state.update(overrides)
    return state


def test_scenario_07_routes_researcher_with_no_findings(monkeypatch):
    fake = FakeChatModel(structured_responses=[RouteDecision(next=RouteTarget.RESEARCHER, reason="r")])
    monkeypatch.setattr(supervisor_mod, "ChatOpenAI", lambda **kw: fake)
    assert supervisor_mod.supervisor_node(_state())["route"] == RouteTarget.RESEARCHER


def test_scenario_08_routes_writer_once_findings_sufficient(monkeypatch):
    from app.schemas import ResearchFinding

    fake = FakeChatModel(structured_responses=[RouteDecision(next=RouteTarget.WRITER, reason="w")])
    monkeypatch.setattr(supervisor_mod, "ChatOpenAI", lambda **kw: fake)
    state = _state(findings=[ResearchFinding(kind="web", summary="x")])
    assert supervisor_mod.supervisor_node(state)["route"] == RouteTarget.WRITER


def test_scenario_09_routes_human_approval_once_draft_ready():
    state = _state(draft=_draft())
    assert supervisor_mod.supervisor_node(state)["route"] == RouteTarget.HUMAN_APPROVAL


def test_scenario_10_routes_end_once_approval_filed():
    state = _state(approval=object())
    assert supervisor_mod.supervisor_node(state)["route"] == RouteTarget.END


def test_scenario_11_forces_writer_at_iteration_budget():
    state = _state(iterations=99)
    assert supervisor_mod.supervisor_node(state)["route"] == RouteTarget.WRITER


# --- Memory recall scenarios (12-16) --------------------------------------

def test_scenario_12_recalls_recent_turns_in_order():
    manager = MemoryManager(InMemoryEpisodicStore(), InMemorySemanticStore())
    manager.record_turn("s1", "user", "Tell me about DataSphere 1")
    manager.record_turn("s1", "assistant", "DataSphere 1 leads the EU AI market")
    history = manager.recall_history("s1")
    assert history[0]["role"] == "user" and history[1]["role"] == "assistant"


def test_scenario_13_semantic_recall_matches_relevant_memory():
    manager = MemoryManager(InMemoryEpisodicStore(), InMemorySemanticStore())
    manager.record_turn("s1", "assistant", "QuantumSoft 2 churn rate rose to 12% in Q2")
    manager.record_turn("s1", "assistant", "It was sunny in Berlin yesterday")
    hits = manager.recall_semantic("QuantumSoft churn rate")
    assert hits and "QuantumSoft" in hits[0]["content"]


def test_scenario_14_memory_sessions_do_not_leak():
    manager = MemoryManager(InMemoryEpisodicStore(), InMemorySemanticStore())
    manager.record_turn("session-a", "user", "secret A")
    manager.record_turn("session-b", "user", "secret B")
    assert manager.recall_history("session-a")[0]["content"] == "secret A"
    assert manager.recall_history("session-b")[0]["content"] == "secret B"


def test_scenario_15_history_limit_returns_most_recent():
    manager = MemoryManager(InMemoryEpisodicStore(), InMemorySemanticStore())
    for i in range(5):
        manager.record_turn("s1", "user", f"turn {i}")
    assert manager.recall_history("s1", limit=2)[-1]["content"] == "turn 4"


def test_scenario_16_semantic_recall_empty_for_unrelated_query():
    manager = MemoryManager(InMemoryEpisodicStore(), InMemorySemanticStore())
    manager.record_turn("s1", "assistant", "VisionTech 3 launched a new BI product")
    assert manager.recall_semantic("unrelated topic xyz") == []


# --- Report generation / compliance scenarios (17-20) ---------------------

def test_scenario_17_report_flags_email_as_sensitive():
    assert contains_sensitive_data("Contact billing@datasphere.example.com")


def test_scenario_18_report_clean_text_not_flagged():
    assert not contains_sensitive_data("Quarterly revenue increased 8%")


def test_scenario_19_finalize_draft_sets_flag_before_approval():
    draft = finalize_draft(_draft(summary="reach out to sales@quantumsoft.example.com"))
    assert draft.contains_sensitive_data is True


def test_scenario_20_approval_workflow_pending_then_approved():
    request = approval_store.create_approval_request("s1", "Final Report", "# Final Report")
    assert request.status.value == "pending"
    decided = approval_store.decide(request.approval_id, approved=True, reviewer="Compliance Officer")
    assert decided.status.value == "approved"
    assert decided not in approval_store.list_pending()
