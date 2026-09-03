"""Applies PII redaction to outgoing model/report text before it is
returned to a client or written to logs/reports (belt-and-suspenders
vs. input-side redaction in `pipeline.check_prompt`).

Ported unchanged from Milestone-4 (`src/guardrails/response_filter.py`).
"""
from __future__ import annotations

from app.guardrails import pii


def filter_response(text: str) -> str:
    """Redact any PII that leaked into a generated response."""
    return pii.redact(text)
