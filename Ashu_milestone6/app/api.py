"""FastAPI backend (M5 Step 1, hardened in M6): thin wrapper around the
existing M3 LangGraph pipeline (`app/runner.py`) - streams the multi-agent
workflow over Server-Sent Events and exposes the human-approval queue. No
agent/tool/business logic lives here; every endpoint body just calls what
M3 already built and (de)serializes it through Pydantic models.

Security (M6 Step 3 - see app/auth.py and app/guardrails/):
  - Every route requires an `X-API-Key` header (M5 baseline, unchanged).
  - Every business route ALSO requires a valid JWT bearer token (M6 -
    required second layer, not a replacement for the API key). Only
    `/`, `/health`, and `POST /auth/login` are reachable on the API key
    alone, since a client can't hold a token before it has one.
  - Every `/research*` request is screened by the M4-derived guardrail
    pipeline (`app.guardrails.check_prompt`) before it reaches the graph:
    prompt-injection/jailbreak/toxicity -> 400, PII -> redacted and run.

Run with: uvicorn app.api:api --reload
"""
from __future__ import annotations

import json

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.auth import issue_demo_token, require_api_key, require_jwt
from app.graph.state import GraphState
from app.guardrails import check_prompt
from app.instrumentation import get_tracer, new_trace_id
from app.runner import run_research_stream
from app.tools.approval_store import decide, get_approval, list_pending

api = FastAPI(
    title="Enterprise AI Multi-Agent Research Assistant",
    description="M5/M6 API layer wrapping the M3/M4 Supervisor/Researcher/Writer/Human-Approval pipeline.",
    dependencies=[Depends(require_api_key)],  # required baseline: every route needs X-API-Key
)


@api.get("/")
def root():
    return {"status": "ok", "service": "enterprise-ai-research-assistant"}


class ResearchRequest(BaseModel):
    task: str = Field(..., min_length=3, max_length=4000, description="The research question/task")
    session_id: str | None = Field(default=None, max_length=200)


class DecisionRequest(BaseModel):
    approved: bool
    reviewer: str = Field(..., min_length=1, max_length=200)
    comment: str | None = Field(default=None, max_length=2000)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


def _serialize_state(state: GraphState) -> dict:
    out = dict(state)
    out["findings"] = [f.model_dump(mode="json") for f in out.get("findings", [])]
    if out.get("draft") is not None:
        out["draft"] = out["draft"].model_dump(mode="json")
    if out.get("approval") is not None:
        out["approval"] = out["approval"].model_dump(mode="json")
    if out.get("route") is not None:
        out["route"] = out["route"].value
    return out


def _guard(task: str, trace_id: str) -> str:
    """Runs the M4-derived guardrail pipeline on an inbound research task.
    Blocks (HTTP 400) on prompt-injection/jailbreak/toxicity; returns the
    PII-redacted task text when PII is present but the request is otherwise
    safe; returns the task unchanged when it's clean."""
    decision = check_prompt(task, trace_id=trace_id)
    if decision.action == "block":
        raise HTTPException(
            status_code=400,
            detail=f"Request blocked by guardrails (categories: {', '.join(decision.categories)}).",
        )
    return decision.redacted_prompt if decision.action == "redact" else task


@api.post("/research/stream")
def research_stream(payload: ResearchRequest, _subject: str = Depends(require_jwt)):
    trace_id = new_trace_id()
    task = _guard(payload.task, trace_id)

    def event_source():
        try:
            for state in run_research_stream(task, session_id=payload.session_id, trace_id=trace_id):
                yield f"data: {json.dumps(_serialize_state(state))}\n\n"
            yield "event: done\ndata: {}\n\n"
        except Exception as exc:  # noqa: BLE001 - surface pipeline failures to the SSE client instead of a bare 500
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        event_source(), media_type="text/event-stream", headers={"X-Trace-Id": trace_id}
    )


@api.post("/research")
async def research_sync(payload: ResearchRequest, _subject: str = Depends(require_jwt)):
    """Non-streaming convenience endpoint: runs the graph to completion in a
    threadpool (the pipeline itself is synchronous) and returns the final
    state as JSON."""
    trace_id = new_trace_id()
    task = _guard(payload.task, trace_id)

    def _run() -> GraphState:
        final_state: GraphState = {}
        for state in run_research_stream(task, session_id=payload.session_id, trace_id=trace_id):
            final_state = state
        return final_state

    try:
        final_state = await run_in_threadpool(_run)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Pipeline error: {exc}") from exc
    return _serialize_state(final_state)


@api.get("/approvals")
def approvals_list(_subject: str = Depends(require_jwt)):
    with get_tracer().span("api.approvals_list", agent="api"):
        return [a.model_dump(mode="json") for a in list_pending()]


@api.get("/approvals/{approval_id}")
def approvals_get(approval_id: str, _subject: str = Depends(require_jwt)):
    approval = get_approval(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="approval not found")
    return approval.model_dump(mode="json")


@api.post("/approvals/{approval_id}/decision")
def approvals_decide(approval_id: str, payload: DecisionRequest, _subject: str = Depends(require_jwt)):
    """Extra-sensitive action (approves/rejects distribution of a report):
    requires the baseline API key (applied app-wide) *and* a valid JWT."""
    with get_tracer().span("api.approvals_decide", agent="api") as span:
        try:
            approval = decide(approval_id, payload.approved, payload.reviewer, payload.comment)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        span.set_metadata(approval_id=approval_id, approved=payload.approved, reviewer=payload.reviewer)
    return approval.model_dump(mode="json")


@api.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest):
    """Required JWT layer, M6: exchanges the hardcoded demo user's
    credentials (env-configured, never hardcoded in source) for a signed,
    short-lived bearer token that every business route now demands. Still
    behind the API-key dependency above (this route can't require its own
    JWT - it's the one that issues them)."""
    token = issue_demo_token(payload.username, payload.password)
    return TokenResponse(access_token=token)


@api.get("/health")
def health():
    return {"status": "ok"}
