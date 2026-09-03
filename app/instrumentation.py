"""LLMOps instrumentation: lightweight span/trace logging for every
agent/tool call - name, duration, token counts, estimated cost, and a
trace_id shared across every span in one request.

Mirrors the 25 Jul LLMOps lab's `instrumentation.py` shape
(`get_tracer()` / `estimate_cost_usd()`) adapted to this project: one JSON
line per span appended to `logs/spans.jsonl`, which `app/monitoring_dashboard.py`
reads to compute p50/p95 latency, cost, error rate, and request volume.

Usage:
    from app.instrumentation import get_tracer, trace

    with trace() as trace_id:               # opens once per incoming request
        with get_tracer().span("writer.compile_report", agent="writer") as span:
            response = llm.invoke(...)
            span.record_llm_usage(model, prompt_text=..., completion_text=...)
"""
from __future__ import annotations

import contextlib
import contextvars
import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
SPAN_LOG_PATH = LOG_DIR / "spans.jsonl"

_write_lock = threading.Lock()

# USD per 1M tokens (input, output). Approximate public list pricing;
# good enough for relative cost tracking / dashboarding, not billing-grade.
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-3.5-turbo": (0.50, 1.50),
    "text-embedding-3-small": (0.02, 0.0),
    "text-embedding-3-large": (0.13, 0.0),
}
_DEFAULT_PRICING = (0.15, 0.60)  # fall back to gpt-4o-mini rates


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Reusable cost estimator (same signature/shape as the LLMOps lab's
    `estimate_cost_usd`)."""
    in_rate, out_rate = _MODEL_PRICING.get(model, _DEFAULT_PRICING)
    return (prompt_tokens / 1_000_000) * in_rate + (completion_tokens / 1_000_000) * out_rate


def count_tokens(text: str, model: str = "gpt-4o-mini") -> int:
    """Best-effort token count: tiktoken when available, else a
    ~4-chars-per-token heuristic. Fine for cost dashboards, not for billing."""
    if not text:
        return 0
    try:
        import tiktoken

        try:
            enc = tiktoken.encoding_for_model(model)
        except KeyError:
            enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)


_trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)


def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]


@contextlib.contextmanager
def trace(trace_id: str | None = None):
    """Establishes the trace_id every span opened inside this `with` block
    (same thread) will share. Call once per incoming request."""
    tid = trace_id or new_trace_id()
    token = _trace_id_var.set(tid)
    try:
        yield tid
    finally:
        _trace_id_var.reset(token)


def current_trace_id() -> str:
    return _trace_id_var.get() or "no-trace"


def _write(record: dict) -> None:
    line = json.dumps(record, default=str)
    with _write_lock:
        with open(SPAN_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")


class Span:
    """One agent/tool call. Use as a context manager; duration is measured
    automatically, cost is computed from whatever token counts get recorded
    via `record_llm_usage` before the block exits."""

    def __init__(self, name: str, agent: str = "", trace_id: str | None = None):
        self.name = name
        self.agent = agent
        self.trace_id = trace_id or current_trace_id()
        self.span_id = uuid.uuid4().hex[:12]
        self.model = ""
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.metadata: dict = {}
        self._start = 0.0

    def record_llm_usage(
        self,
        model: str,
        prompt_text: str = "",
        completion_text: str = "",
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
    ) -> None:
        """Attach token/cost info to this span. Pass explicit counts when the
        provider returns real usage metadata; otherwise pass the raw prompt/
        completion text and it's estimated via `count_tokens`."""
        self.model = model
        self.prompt_tokens = prompt_tokens if prompt_tokens is not None else count_tokens(prompt_text, model)
        self.completion_tokens = (
            completion_tokens if completion_tokens is not None else count_tokens(completion_text, model)
        )

    def set_metadata(self, **kv) -> None:
        self.metadata.update({k: v for k, v in kv.items() if v is not None})

    def __enter__(self) -> "Span":
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        duration_ms = (time.perf_counter() - self._start) * 1000
        cost = estimate_cost_usd(self.model, self.prompt_tokens, self.completion_tokens) if self.model else 0.0
        record = {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "name": self.name,
            "agent": self.agent,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_ms": round(duration_ms, 2),
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.prompt_tokens + self.completion_tokens,
            "cost_usd": round(cost, 6),
            "status": "error" if exc_type else "ok",
            "error": f"{exc_type.__name__}: {exc}" if exc_type else None,
            "metadata": self.metadata,
        }
        _write(record)
        return False  # never suppress the original exception


class _TracerFacade:
    """Returned by `get_tracer()`. A thin factory so call sites read like
    `get_tracer().span(name, agent=...)`, matching the lab's `get_tracer()`
    naming."""

    def span(self, name: str, agent: str = "") -> Span:
        return Span(name, agent=agent)


def get_tracer() -> _TracerFacade:
    return _TracerFacade()
