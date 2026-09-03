"""Supervisor Agent: plans the task and routes work to Researcher / Writer /
Human Approval using an LLM structured-output decision, with deterministic
guardrails layered on top so the graph always terminates correctly even if
the LLM's judgement call is questionable.
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.graph.state import GraphState
from app.instrumentation import get_tracer
from app.logging_utils import log_event
from app.schemas import RouteDecision, RouteTarget

_SYSTEM_PROMPT = """You are the Supervisor Agent for an enterprise competitor-research
assistant. You do not do research or writing yourself - you decide which specialist
agent should act next: researcher, writer, human_approval, or end.

Guidelines:
- If there is no research yet, route to researcher.
- If research findings exist but are thin/one-sided for the task, route to researcher
  again with more specific instructions.
- Once findings are sufficient to answer the task, route to writer.
- Once a report draft exists, route to human_approval so it can be reviewed before
  distribution (compliance policy).
- Once an approval request has been created, route to end.
"""


def _summarize_state(state: GraphState) -> str:
    findings = state.get("findings", [])
    draft = state.get("draft")
    approval = state.get("approval")
    lines = [
        f"Task: {state.get('task')}",
        f"Research iterations so far: {state.get('iterations', 0)}",
        f"Findings collected: {len(findings)}",
    ]
    for f in findings[-6:]:
        lines.append(f"  - [{f.kind}] {f.summary[:200]}")
    lines.append(f"Draft report exists: {draft is not None}")
    lines.append(f"Approval request exists: {approval is not None}")
    return "\n".join(lines)


def supervisor_node(state: GraphState) -> dict:
    settings = get_settings()
    session_id = state["session_id"]
    findings = state.get("findings", [])
    draft = state.get("draft")
    approval = state.get("approval")
    iterations = state.get("iterations", 0)

    # Deterministic guardrails that don't require an LLM call.
    with get_tracer().span("supervisor.route", agent="supervisor") as span:
        if approval is not None:
            decision = RouteDecision(next=RouteTarget.END, reason="Approval request already created.")
        elif draft is not None:
            decision = RouteDecision(next=RouteTarget.HUMAN_APPROVAL, reason="Draft ready for review.")
        elif iterations >= settings.max_research_iterations:
            decision = RouteDecision(
                next=RouteTarget.WRITER, reason="Reached max research iterations; compiling report."
            )
        else:
            prompt = _summarize_state(state)
            llm = ChatOpenAI(
                model=settings.openai_model, temperature=0, api_key=settings.openai_api_key or "not-set"
            )
            structured_llm = llm.with_structured_output(RouteDecision)
            decision = structured_llm.invoke(
                [
                    SystemMessage(content=_SYSTEM_PROMPT),
                    HumanMessage(content=prompt),
                ]
            )
            span.record_llm_usage(settings.openai_model, prompt_text=prompt, completion_text=decision.model_dump_json())
            # Guardrail: never let the LLM skip straight to writer with zero findings.
            if decision.next == RouteTarget.WRITER and not findings:
                decision = RouteDecision(
                    next=RouteTarget.RESEARCHER,
                    reason="No findings yet; overriding to researcher.",
                    research_instructions=state.get("task"),
                )
        span.set_metadata(session_id=session_id, route=decision.next.value, iterations=iterations)

    log_event(
        session_id=session_id,
        agent="supervisor",
        action="route",
        input_summary=_summarize_state(state),
        output_summary=decision.next.value,
        reason=decision.reason,
    )

    update: dict = {"route": decision.next, "route_reason": decision.reason}
    if decision.next == RouteTarget.RESEARCHER:
        update["research_instructions"] = decision.research_instructions or state.get("task")
    return update
