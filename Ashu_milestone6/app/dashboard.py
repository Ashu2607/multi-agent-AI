"""Streamlit frontend (M5 Step 2) for the Multi-Agent Research Assistant.

This is the end-user UI, not the ops monitoring dashboard - that's the
separate `app/monitoring_dashboard.py` (M5 Step 4). This file talks to the
FastAPI backend (`app/api.py`) over HTTP with an API key, the same way any
other client would - no direct import of the pipeline - so it's a true
client/server split, not a disclosed shortcut.

Run with (backend must already be running on API_BASE_URL):
    streamlit run app/dashboard.py --server.port 8501
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Streamlit puts this script's own folder (app/) at the front of sys.path,
# not the project root, so `import app.*` can't resolve unless we add the
# root ourselves first.
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv(ROOT_DIR / ".env")

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
API_KEY = os.environ.get("API_KEY", "")
DEMO_USERNAME = os.environ.get("DEMO_USERNAME", "demo")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "")
FEEDBACK_LOG_PATH = ROOT_DIR / "logs" / "feedback.jsonl"

st.set_page_config(page_title="Enterprise AI Research Assistant", layout="wide")


def _headers(with_auth: bool = True) -> dict:
    """M6: every business route now requires a JWT bearer token *in addition
    to* X-API-Key (see app/auth.py), so this defaults to sending both -
    `with_auth=False` is only for the couple of routes (root/health) that
    intentionally don't need one."""
    headers = {"X-API-Key": API_KEY}
    if with_auth and st.session_state.get("jwt_token"):
        headers["Authorization"] = f"Bearer {st.session_state['jwt_token']}"
    return headers


def _ensure_jwt() -> None:
    """Best-effort, silent login for the demo user so every API call this UI
    makes (M6: JWT is required on all business routes, not just approve/
    reject - see app/auth.py) works without asking a reviewer to type
    credentials. Failure just means those calls will surface the API's 401."""
    if st.session_state.get("jwt_token") or not DEMO_PASSWORD:
        return
    try:
        r = httpx.post(
            f"{API_BASE_URL}/auth/login",
            json={"username": DEMO_USERNAME, "password": DEMO_PASSWORD},
            headers=_headers(),
            timeout=10,
        )
        if r.status_code == 200:
            st.session_state["jwt_token"] = r.json()["access_token"]
    except httpx.HTTPError:
        pass


def _log_feedback(trace_id: str | None, session_id: str, rating: str) -> None:
    FEEDBACK_LOG_PATH.parent.mkdir(exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "trace_id": trace_id,
        "rating": rating,  # "up" | "down"
    }
    with open(FEEDBACK_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _stream_research(task: str, session_id: str, progress_box) -> tuple[dict, str | None]:
    """POSTs to /research/stream and consumes the SSE feed, updating
    `progress_box` as the Supervisor routes between agents. Returns the
    final state dict and the trace_id the backend assigned this request."""
    final_state: dict = {}
    trace_id = None
    last_route = None
    pending_event = "message"

    with httpx.stream(
        "POST",
        f"{API_BASE_URL}/research/stream",
        json={"task": task, "session_id": session_id},
        headers=_headers(),
        timeout=httpx.Timeout(300.0, connect=10.0),
    ) as response:
        if response.status_code != 200:
            response.read()
            raise RuntimeError(f"Backend returned {response.status_code}: {response.text}")
        trace_id = response.headers.get("X-Trace-Id")

        for line in response.iter_lines():
            if not line:
                continue
            if line.startswith("event:"):
                pending_event = line[len("event:") :].strip()
                continue
            if not line.startswith("data:"):
                continue
            data_str = line[len("data:") :].strip()
            event = pending_event
            pending_event = "message"

            if event == "error":
                payload = json.loads(data_str) if data_str else {}
                raise RuntimeError(payload.get("error", "Unknown pipeline error"))
            if event == "done":
                continue

            state = json.loads(data_str)
            final_state = state
            route = state.get("route")
            if route and route != last_route:
                progress_box.write(f"**-> routed to `{route}`** — {state.get('route_reason', '')}")
                last_route = route

    return final_state, trace_id


if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "jwt_token" not in st.session_state:
    st.session_state.jwt_token = None

_ensure_jwt()

st.title("AI-Powered Multi-Agent Research Assistant")
st.caption("Supervisor -> Researcher -> Writer -> Human Approval, served via FastAPI + LangGraph.")

if not API_KEY:
    st.error("API_KEY is not set - copy .env.example to .env and set API_KEY (must match the backend's).")

tab_research, tab_approvals = st.tabs(["Run Research", "Approval Queue"])

with tab_research:
    with st.form("research_form"):
        task = st.text_area(
            "Research request",
            placeholder="e.g. Compare pricing and Q1 2025 growth between DataSphere 1 and QuantumSoft 2",
            height=100,
        )
        submitted = st.form_submit_button("Run")

    if submitted and task.strip():
        progress_box = st.status("Running multi-agent workflow via FastAPI...", expanded=True)
        try:
            final_state, trace_id = _stream_research(task, st.session_state.session_id, progress_box)
            progress_box.update(label="Workflow complete", state="complete")
        except (RuntimeError, httpx.HTTPError) as exc:
            progress_box.update(label="Workflow failed", state="error")
            st.error(f"Could not reach the backend or the pipeline errored: {exc}")
            final_state, trace_id = {}, None

        draft = final_state.get("draft")
        approval = final_state.get("approval")
        st.session_state["last_trace_id"] = trace_id

        if draft:
            st.subheader(draft["title"])
            if draft.get("contains_sensitive_data"):
                st.warning("Possible sensitive data detected in this draft - review carefully.")
            st.markdown(draft["executive_summary"])
            for section in draft.get("sections", []):
                with st.expander(section["heading"], expanded=True):
                    st.markdown(section["content"])
            if draft.get("sources"):
                st.markdown("**Sources:** " + ", ".join(draft["sources"]))

            st.markdown("**Was this report useful?**")
            fcol1, fcol2, _ = st.columns([1, 1, 6])
            with fcol1:
                if st.button("👍", key="fb_up"):
                    _log_feedback(trace_id, st.session_state.session_id, "up")
                    st.toast("Thanks for the feedback!")
            with fcol2:
                if st.button("👎", key="fb_down"):
                    _log_feedback(trace_id, st.session_state.session_id, "down")
                    st.toast("Thanks for the feedback!")

        if approval:
            st.success(f"Filed for human approval — approval_id: `{approval['approval_id']}`")

        with st.expander("Research findings (raw)"):
            for f in final_state.get("findings", []):
                st.markdown(f"- **[{f['kind']}]** {f['summary']}")

with tab_approvals:
    st.subheader("Reports pending review")
    st.caption(
        "This is the M3 Human-in-the-Loop gate, made clickable: every report a Writer "
        "compiles is filed here and must be approved or rejected before it counts as delivered."
    )
    try:
        pending = httpx.get(f"{API_BASE_URL}/approvals", headers=_headers(), timeout=10).json()
    except httpx.HTTPError as exc:
        pending = []
        st.error(f"Could not reach the backend: {exc}")

    if not pending:
        st.info("Nothing pending approval.")
    else:
        options = {f"{a['report_title']} ({a['approval_id'][:8]})": a["approval_id"] for a in pending}
        choice = st.selectbox("Select a report", list(options.keys()))
        approval_id = options[choice]
        approval = httpx.get(f"{API_BASE_URL}/approvals/{approval_id}", headers=_headers(), timeout=10).json()
        st.markdown(approval["report_markdown"])

        col1, col2 = st.columns(2)
        reviewer = st.text_input("Reviewer name", key="reviewer")
        comment = st.text_input("Comment (optional)", key="comment")
        with col1:
            if st.button("Approve", type="primary", disabled=not reviewer):
                r = httpx.post(
                    f"{API_BASE_URL}/approvals/{approval_id}/decision",
                    json={"approved": True, "reviewer": reviewer, "comment": comment},
                    headers=_headers(with_auth=True),
                    timeout=10,
                )
                if r.status_code == 200:
                    st.rerun()
                else:
                    st.error(f"Approve failed ({r.status_code}): {r.text}")
        with col2:
            if st.button("Reject", disabled=not reviewer):
                r = httpx.post(
                    f"{API_BASE_URL}/approvals/{approval_id}/decision",
                    json={"approved": False, "reviewer": reviewer, "comment": comment},
                    headers=_headers(with_auth=True),
                    timeout=10,
                )
                if r.status_code == 200:
                    st.rerun()
                else:
                    st.error(f"Reject failed ({r.status_code}): {r.text}")
