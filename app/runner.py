"""Shared entry point used by the CLI, FastAPI, and Streamlit front-ends to
run one research session through the compiled LangGraph and persist memory.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator

from app.graph.build_graph import get_graph
from app.graph.state import GraphState
from app.instrumentation import get_tracer, trace
from app.memory.manager import get_memory_manager


def new_session_id() -> str:
    return str(uuid.uuid4())


def run_research_stream(task: str, session_id: str | None = None, trace_id: str | None = None) -> Iterator[GraphState]:
    """Streams full state snapshots as the graph progresses. The last
    yielded value is the final state (contains draft + approval once done).

    Wrapped in a single `pipeline.run` span (LLMOps instrumentation) that
    shares one trace_id with every agent/tool span opened underneath it -
    that's the row the monitoring dashboard treats as "one request" for
    latency/error-rate/volume, while cost is summed across every span on
    the same trace_id.
    """
    session_id = session_id or new_session_id()
    memory = get_memory_manager()
    memory.record_turn(session_id, "user", task)

    graph = get_graph()
    initial_state: GraphState = {
        "session_id": session_id,
        "task": task,
        "research_instructions": None,
        "findings": [],
        "iterations": 0,
        "draft": None,
        "approval": None,
        "route": None,
        "route_reason": "",
        "report_path": None,
    }

    final_state: GraphState = initial_state
    with trace(trace_id) as tid, get_tracer().span("pipeline.run", agent="pipeline") as span:
        span.set_metadata(session_id=session_id, task=task[:200], trace_id=tid)
        for state in graph.stream(initial_state, stream_mode="values"):
            final_state = state
            yield state
        draft = final_state.get("draft")
        approval = final_state.get("approval")
        span.set_metadata(
            iterations=final_state.get("iterations", 0),
            n_findings=len(final_state.get("findings", [])),
            has_draft=draft is not None,
            has_approval=approval is not None,
        )

    if draft is not None:
        memory.record_turn(session_id, "assistant", draft.executive_summary)


def run_research(task: str, session_id: str | None = None) -> GraphState:
    """Non-streaming convenience wrapper: runs the graph to completion."""
    final_state: GraphState = {}
    for state in run_research_stream(task, session_id=session_id):
        final_state = state
    return final_state
