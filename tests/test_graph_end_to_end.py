"""End-to-end multi-agent collaboration test: Supervisor -> Researcher ->
Supervisor -> Writer -> Supervisor -> Human Approval -> END, with every LLM
call and external tool call mocked so it runs offline and deterministically.
"""
from __future__ import annotations

from tests.conftest import FakeChatModel

import app.agents.researcher as researcher_mod  # noqa: E402
import app.agents.supervisor as supervisor_mod
import app.agents.writer as writer_mod
from app.graph.build_graph import build_graph
from app.schemas import (
    ReportDraft,
    ReportSection,
    ResearchFinding,
    RouteDecision,
    RouteTarget,
    SQLQueryResult,
    WebSearchResult,
)


class _ResearchPlanStub:
    web_query = "DataSphere 1 news"
    sql_question = "What is DataSphere 1's market share?"
    kb_query = "compliance policy for reports"


def test_full_workflow_reaches_human_approval(monkeypatch):
    # Supervisor: researcher first, then writer, once findings exist.
    supervisor_llm = FakeChatModel(
        structured_responses=[
            RouteDecision(next=RouteTarget.RESEARCHER, reason="need data", research_instructions="go"),
            RouteDecision(next=RouteTarget.WRITER, reason="enough data"),
        ]
    )
    monkeypatch.setattr(supervisor_mod, "ChatOpenAI", lambda **kwargs: supervisor_llm)

    # Researcher: stub the planning LLM and all three tool calls.
    monkeypatch.setattr(researcher_mod, "_plan_research", lambda instructions: _ResearchPlanStub())
    monkeypatch.setattr(
        researcher_mod,
        "run_web_search",
        lambda query, session_id="-": [WebSearchResult(title="News", url="http://x", content="DataSphere grew")],
    )
    monkeypatch.setattr(
        researcher_mod,
        "run_text_to_sql",
        lambda question, session_id="-": SQLQueryResult(
            question=question, sql="SELECT 1", columns=["x"], rows=[[1]], row_count=1
        ),
    )
    monkeypatch.setattr(researcher_mod, "search_knowledge_base", lambda query, session_id="-": [])

    # Writer: stub the report-compiling LLM.
    draft = ReportDraft(
        title="DataSphere 1 Competitive Analysis",
        executive_summary="DataSphere 1 is growing steadily.",
        sections=[ReportSection(heading="Market Position", content="Strong in EU market.")],
    )
    writer_llm = FakeChatModel(structured_responses=[draft])
    monkeypatch.setattr(writer_mod, "ChatOpenAI", lambda **kwargs: writer_llm)

    graph = build_graph()
    final_state = graph.invoke(
        {
            "session_id": "test-session",
            "task": "Research DataSphere 1",
            "findings": [],
            "iterations": 0,
        }
    )

    assert final_state["route"] == RouteTarget.END
    assert final_state["draft"].title == "DataSphere 1 Competitive Analysis"
    assert final_state["approval"] is not None
    assert final_state["approval"].status.value == "pending"
    assert final_state["iterations"] == 1
    assert len(final_state["findings"]) >= 2  # web + sql findings recorded


def test_workflow_forces_writer_after_max_iterations(monkeypatch):
    """Even if the Supervisor's LLM keeps asking for more research, the
    deterministic guardrail must force a writer route once the iteration
    budget (app.config.Settings.max_research_iterations) is exhausted."""
    supervisor_llm = FakeChatModel(
        structured_responses=[
            RouteDecision(next=RouteTarget.RESEARCHER, reason="more", research_instructions="go")
        ]
    )
    monkeypatch.setattr(supervisor_mod, "ChatOpenAI", lambda **kwargs: supervisor_llm)
    monkeypatch.setattr(researcher_mod, "_plan_research", lambda instructions: _ResearchPlanStub())
    monkeypatch.setattr(researcher_mod, "run_web_search", lambda query, session_id="-": [])
    monkeypatch.setattr(
        researcher_mod,
        "run_text_to_sql",
        lambda question, session_id="-": SQLQueryResult(
            question=question, sql="SELECT 1", columns=[], rows=[], row_count=0, error="boom"
        ),
    )
    monkeypatch.setattr(researcher_mod, "search_knowledge_base", lambda query, session_id="-": [])

    draft = ReportDraft(title="T", executive_summary="s", sections=[ReportSection(heading="h", content="c")])
    writer_llm = FakeChatModel(structured_responses=[draft])
    monkeypatch.setattr(writer_mod, "ChatOpenAI", lambda **kwargs: writer_llm)

    from app.config import get_settings

    max_iters = get_settings().max_research_iterations

    graph = build_graph()
    final_state = graph.invoke(
        {"session_id": "test-session-2", "task": "Research X", "findings": [], "iterations": 0}
    )

    assert final_state["iterations"] == max_iters
    assert final_state["draft"] is not None
