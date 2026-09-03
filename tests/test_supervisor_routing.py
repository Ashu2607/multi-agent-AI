from __future__ import annotations

from tests.conftest import FakeChatModel

import app.agents.supervisor as supervisor
from app.schemas import ReportDraft, ReportSection, RouteDecision, RouteTarget


def _base_state(**overrides):
    state = {
        "session_id": "s1",
        "task": "Research DataSphere 1's competitive position",
        "findings": [],
        "iterations": 0,
        "draft": None,
        "approval": None,
    }
    state.update(overrides)
    return state


def test_routes_to_human_approval_when_draft_exists_no_llm_needed(monkeypatch):
    draft = ReportDraft(title="T", executive_summary="s", sections=[ReportSection(heading="h", content="c")])
    result = supervisor.supervisor_node(_base_state(draft=draft))
    assert result["route"] == RouteTarget.HUMAN_APPROVAL


def test_routes_to_end_when_approval_exists_no_llm_needed():
    result = supervisor.supervisor_node(_base_state(approval=object()))
    assert result["route"] == RouteTarget.END


def test_routes_to_writer_when_max_iterations_reached_no_llm_needed():
    result = supervisor.supervisor_node(_base_state(iterations=3))
    assert result["route"] == RouteTarget.WRITER


def test_routes_to_researcher_per_llm_decision(monkeypatch):
    fake_llm = FakeChatModel(
        structured_responses=[
            RouteDecision(next=RouteTarget.RESEARCHER, reason="need data", research_instructions="dig in")
        ]
    )
    monkeypatch.setattr(supervisor, "ChatOpenAI", lambda **kwargs: fake_llm)
    result = supervisor.supervisor_node(_base_state())
    assert result["route"] == RouteTarget.RESEARCHER
    assert result["research_instructions"] == "dig in"


def test_overrides_llm_writer_decision_when_no_findings(monkeypatch):
    fake_llm = FakeChatModel(
        structured_responses=[RouteDecision(next=RouteTarget.WRITER, reason="looks ready")]
    )
    monkeypatch.setattr(supervisor, "ChatOpenAI", lambda **kwargs: fake_llm)
    result = supervisor.supervisor_node(_base_state(findings=[]))
    assert result["route"] == RouteTarget.RESEARCHER


def test_allows_writer_decision_when_findings_present(monkeypatch):
    from app.schemas import ResearchFinding

    fake_llm = FakeChatModel(
        structured_responses=[RouteDecision(next=RouteTarget.WRITER, reason="enough data")]
    )
    monkeypatch.setattr(supervisor, "ChatOpenAI", lambda **kwargs: fake_llm)
    finding = ResearchFinding(kind="web", summary="some finding")
    result = supervisor.supervisor_node(_base_state(findings=[finding]))
    assert result["route"] == RouteTarget.WRITER
