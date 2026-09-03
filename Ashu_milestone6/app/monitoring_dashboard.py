"""Ops monitoring dashboard (M5 Step 4) - ***not*** the end-user UI.

Reads `logs/spans.jsonl` (written by `app/instrumentation.py`, wired into
every agent/tool call in `app/agents/*` and `app/tools/*`) and visualizes
p50/p95 latency, cost over time, error rate, and request volume - the same
`load_log()` / `percentile()` shape as the 25 Jul LLMOps lab's
`dashboard.py`, pointed at this project's span log instead.

Run with:
    streamlit run app/monitoring_dashboard.py --server.port 8502
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

SPAN_LOG_PATH = ROOT_DIR / "logs" / "spans.jsonl"

# Palette slots (validated categorical order - see dataviz skill): blue is
# categorical slot 1 (p50 / primary magnitude), orange is slot 2 (p95).
# Status colors are the fixed, never-themed good/critical pair.
COLOR_P50 = "#2a78d6"
COLOR_P95 = "#eb6834"
COLOR_SEQUENTIAL = "#2a78d6"
COLOR_GOOD = "#0ca30c"
COLOR_CRITICAL = "#d03b3b"
GRIDLINE = "#e1e0d9"
MUTED = "#898781"
PRIMARY_INK = "#0b0b0b"

st.set_page_config(page_title="LLMOps Monitoring Dashboard", layout="wide")


@st.cache_data(ttl=30)
def load_log(path: str) -> pd.DataFrame:
    """Reads the JSONL span log into a DataFrame. Cached for 30s so a demo
    doesn't re-read the whole file on every widget interaction, but still
    picks up freshly logged requests during a live walkthrough."""
    rows = []
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    return df.dropna(subset=["timestamp"]).sort_values("timestamp")


def percentile(series: pd.Series, q: float) -> float:
    if series.empty:
        return 0.0
    return float(np.percentile(series, q))


def _empty_state() -> None:
    st.title("LLMOps Monitoring Dashboard")
    st.warning(
        f"No spans logged yet at `{SPAN_LOG_PATH}`. Run a few requests through the UI "
        "(`streamlit run app/dashboard.py`) or the API first - this dashboard reads real "
        "telemetry only, it never falls back to sample data."
    )


df = load_log(str(SPAN_LOG_PATH))
if df.empty:
    _empty_state()
    st.stop()

requests_df = df[df["name"] == "pipeline.run"].copy()
if requests_df.empty:
    _empty_state()
    st.stop()

# Cost is summed across *every* span sharing a trace_id (every agent/tool
# call inside that request), then attached back to that request's row -
# so "cost per request" reflects the whole Supervisor->...->Human Approval
# run, not just the top-level span.
cost_by_trace = df.groupby("trace_id")["cost_usd"].sum()
requests_df["request_cost_usd"] = requests_df["trace_id"].map(cost_by_trace).fillna(0.0)

st.title("LLMOps Monitoring Dashboard")
st.caption(
    "Real telemetry from `logs/spans.jsonl` - one row per agent/tool call, grouped into "
    "requests by trace_id. Refreshes automatically every 30s."
)

# ---- Sidebar filters ---------------------------------------------------
with st.sidebar:
    st.header("Filters")
    n_requests = len(requests_df)
    lookback = st.selectbox("Show", ["All requests", "Last 25", "Last 50", "Last 100"], index=0)
    if lookback != "All requests":
        n = int(lookback.split()[-1])
        requests_df = requests_df.tail(n)
    st.caption(f"{n_requests} total logged requests in the file; {len(requests_df)} shown.")

# ---- Stat tiles ----------------------------------------------------------
p50 = percentile(requests_df["duration_ms"], 50)
p95 = percentile(requests_df["duration_ms"], 95)
error_rate = 100.0 * (requests_df["status"] == "error").mean() if len(requests_df) else 0.0
total_cost = requests_df["request_cost_usd"].sum()
total_requests = len(requests_df)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Requests", f"{total_requests}")
c2.metric("p50 Latency", f"{p50:,.0f} ms")
c3.metric("p95 Latency", f"{p95:,.0f} ms")
c4.metric("Error Rate", f"{error_rate:.1f}%")
c5.metric("Total Cost", f"${total_cost:,.4f}")

st.divider()

# ---- Latency over time (per request, with p50/p95 reference lines) ------
left, right = st.columns(2)

with left:
    st.subheader("Latency per request")
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=requests_df["timestamp"],
            y=requests_df["duration_ms"],
            mode="markers+lines",
            name="request latency",
            line=dict(color=COLOR_SEQUENTIAL, width=2),
            marker=dict(size=8, color=COLOR_SEQUENTIAL),
            hovertemplate="%{x|%H:%M:%S}<br>%{y:.0f} ms<extra></extra>",
        )
    )
    fig.add_hline(y=p50, line=dict(color=COLOR_P50, width=2, dash="dash"), annotation_text="p50", annotation_position="top left")
    fig.add_hline(y=p95, line=dict(color=COLOR_P95, width=2, dash="dash"), annotation_text="p95", annotation_position="top left")
    fig.update_layout(
        template="plotly_white",
        height=360,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title=None,
        yaxis_title="duration (ms)",
        showlegend=False,
        plot_bgcolor="#fcfcfb",
        paper_bgcolor="#fcfcfb",
        font=dict(color=PRIMARY_INK),
    )
    fig.update_xaxes(gridcolor=GRIDLINE, showline=True, linecolor=MUTED)
    fig.update_yaxes(gridcolor=GRIDLINE, showline=True, linecolor=MUTED)
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("Request volume over time")
    volume = requests_df.set_index("timestamp").resample("5min").size().reset_index(name="count")
    fig = go.Figure(
        go.Bar(x=volume["timestamp"], y=volume["count"], marker_color=COLOR_SEQUENTIAL, hovertemplate="%{x|%H:%M}<br>%{y} requests<extra></extra>")
    )
    fig.update_layout(
        template="plotly_white",
        height=360,
        margin=dict(l=10, r=10, t=10, b=10),
        yaxis_title="requests / 5 min",
        plot_bgcolor="#fcfcfb",
        paper_bgcolor="#fcfcfb",
        font=dict(color=PRIMARY_INK),
    )
    fig.update_xaxes(gridcolor=GRIDLINE, showline=True, linecolor=MUTED)
    fig.update_yaxes(gridcolor=GRIDLINE, showline=True, linecolor=MUTED)
    st.plotly_chart(fig, use_container_width=True)

left2, right2 = st.columns(2)

with left2:
    st.subheader("Cost over time")
    cost_series = requests_df.set_index("timestamp")["request_cost_usd"].resample("5min").sum().reset_index()
    fig = go.Figure(
        go.Bar(
            x=cost_series["timestamp"],
            y=cost_series["request_cost_usd"],
            marker_color=COLOR_SEQUENTIAL,
            hovertemplate="%{x|%H:%M}<br>$%{y:.4f}<extra></extra>",
        )
    )
    fig.update_layout(
        template="plotly_white",
        height=360,
        margin=dict(l=10, r=10, t=10, b=10),
        yaxis_title="cost ($) / 5 min",
        plot_bgcolor="#fcfcfb",
        paper_bgcolor="#fcfcfb",
        font=dict(color=PRIMARY_INK),
    )
    fig.update_xaxes(gridcolor=GRIDLINE, showline=True, linecolor=MUTED)
    fig.update_yaxes(gridcolor=GRIDLINE, showline=True, linecolor=MUTED)
    st.plotly_chart(fig, use_container_width=True)

with right2:
    st.subheader("Request outcomes")
    ok_count = int((requests_df["status"] == "ok").sum())
    error_count = int((requests_df["status"] == "error").sum())
    fig = go.Figure(
        go.Pie(
            labels=["ok", "error"],
            values=[ok_count, error_count],
            marker_colors=[COLOR_GOOD, COLOR_CRITICAL],
            hole=0.55,
            hovertemplate="%{label}: %{value} (%{percent})<extra></extra>",
        )
    )
    fig.update_layout(
        template="plotly_white",
        height=360,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="#fcfcfb",
        font=dict(color=PRIMARY_INK),
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---- Per-span breakdown: where time and money actually go ----------------
st.subheader("Cost & latency by span (every agent/tool call, not just the top-level request)")
by_span = (
    df.groupby(["agent", "name"])
    .agg(
        calls=("span_id", "count"),
        avg_duration_ms=("duration_ms", "mean"),
        p95_duration_ms=("duration_ms", lambda s: percentile(s, 95)),
        total_cost_usd=("cost_usd", "sum"),
        errors=("status", lambda s: int((s == "error").sum())),
    )
    .reset_index()
    .sort_values("total_cost_usd", ascending=False)
)
by_span["avg_duration_ms"] = by_span["avg_duration_ms"].round(1)
by_span["p95_duration_ms"] = by_span["p95_duration_ms"].round(1)
by_span["total_cost_usd"] = by_span["total_cost_usd"].round(6)
st.dataframe(by_span, use_container_width=True, hide_index=True)

with st.expander("Raw span log (most recent 200 rows)"):
    st.dataframe(
        df.sort_values("timestamp", ascending=False).head(200)[
            ["timestamp", "trace_id", "name", "agent", "duration_ms", "model", "total_tokens", "cost_usd", "status"]
        ],
        use_container_width=True,
        hide_index=True,
    )
