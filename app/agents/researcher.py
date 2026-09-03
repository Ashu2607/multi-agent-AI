"""Researcher Agent: gathers evidence for the Supervisor's instructions using
the Web Research Tool, the Text-to-SQL workflow, and the internal Knowledge
Base retriever, then records everything as typed ResearchFinding entries.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.graph.state import GraphState
from app.instrumentation import get_tracer
from app.logging_utils import log_event
from app.schemas import ResearchFinding
from app.tools.knowledge_base import search_knowledge_base
from app.tools.text_to_sql import run_text_to_sql
from app.tools.web_search import run_web_search

_SYSTEM_PROMPT = """You are the research planner for a competitor-intelligence assistant.
Given the task/instructions, produce three targeted lookups:
- a web search query for current market/competitor news
- a natural-language question answerable via SQL over competitors, products,
  quarterly_sales, market_news, pricing_comparison tables
- a knowledge-base query for internal policy/product-manual context

Keep each concise and specific to the instructions."""


class ResearchPlan(BaseModel):
    web_query: str = Field(description="Query for live web search")
    sql_question: str = Field(description="Natural-language question for the Text-to-SQL tool")
    kb_query: str = Field(description="Query for the internal knowledge base")


def _plan_research(instructions: str) -> ResearchPlan:
    settings = get_settings()
    with get_tracer().span("researcher.plan", agent="researcher") as span:
        llm = ChatOpenAI(model=settings.openai_model, temperature=0, api_key=settings.openai_api_key or "not-set")
        structured_llm = llm.with_structured_output(ResearchPlan)
        plan = structured_llm.invoke(
            [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=instructions)]
        )
        span.record_llm_usage(settings.openai_model, prompt_text=instructions, completion_text=plan.model_dump_json())
        return plan


def researcher_node(state: GraphState) -> dict:
    session_id = state["session_id"]
    instructions = state.get("research_instructions") or state["task"]

    with get_tracer().span("researcher.iteration", agent="researcher") as node_span:
        plan = _plan_research(instructions)

        findings: list[ResearchFinding] = []

        try:
            web_results = run_web_search(plan.web_query, session_id=session_id)
            for r in web_results:
                findings.append(ResearchFinding(kind="web", summary=f"{r.title}: {r.content[:300]}", detail=r))
        except Exception as exc:  # noqa: BLE001
            findings.append(ResearchFinding(kind="web", summary=f"Web search failed: {exc}"))

        try:
            sql_result = run_text_to_sql(plan.sql_question, session_id=session_id)
            if sql_result.error:
                findings.append(ResearchFinding(kind="sql", summary=f"SQL error: {sql_result.error}", detail=sql_result))
            else:
                findings.append(
                    ResearchFinding(
                        kind="sql",
                        summary=f"Q: {plan.sql_question} -> {sql_result.row_count} row(s) via `{sql_result.sql}`",
                        detail=sql_result,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            findings.append(ResearchFinding(kind="sql", summary=f"Text-to-SQL failed: {exc}"))

        try:
            kb_snippets = search_knowledge_base(plan.kb_query, session_id=session_id)
            for s in kb_snippets:
                findings.append(ResearchFinding(kind="knowledge_base", summary=f"[{s.source}] {s.content[:300]}", detail=s))
        except Exception as exc:  # noqa: BLE001
            findings.append(ResearchFinding(kind="knowledge_base", summary=f"Knowledge base search failed: {exc}"))

        node_span.set_metadata(session_id=session_id, n_findings=len(findings))

    log_event(
        session_id=session_id,
        agent="researcher",
        action="research_iteration",
        input_summary=instructions,
        output_summary=f"{len(findings)} findings collected",
    )

    return {"findings": findings, "iterations": state.get("iterations", 0) + 1}
