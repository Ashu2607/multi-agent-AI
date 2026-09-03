"""Human-in-the-Loop gate: files the compiled report for compliance/manager
sign-off before it can be externally distributed (Policy 1). The graph run
ends once the request is filed; approve/reject happens out-of-band via the
CLI (`review` commands) or the FastAPI `/approvals` endpoints.
"""
from __future__ import annotations

from app.graph.state import GraphState
from app.instrumentation import get_tracer
from app.logging_utils import log_event
from app.tools.approval_store import create_approval_request
from app.tools.report_writer import render_markdown


def human_approval_node(state: GraphState) -> dict:
    session_id = state["session_id"]
    draft = state["draft"]

    with get_tracer().span("human_approval.file_for_review", agent="human_approval") as span:
        markdown = render_markdown(draft)
        approval = create_approval_request(
            session_id=session_id, report_title=draft.title, report_markdown=markdown
        )
        span.set_metadata(session_id=session_id, approval_id=approval.approval_id)

    log_event(
        session_id=session_id,
        agent="human_approval",
        action="file_for_review",
        input_summary=draft.title,
        output_summary=approval.approval_id,
        contains_sensitive_data=draft.contains_sensitive_data,
    )

    return {"approval": approval}
