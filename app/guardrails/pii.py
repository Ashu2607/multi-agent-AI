"""
PII detection and redaction: SSNs, emails, phone numbers, and
credit-card-like numbers.

PII is redacted (not blocked) so the platform can still answer the
underlying question while withholding the sensitive value - unless the
prompt is *also* flagged unsafe (prompt injection/jailbreak/toxicity),
in which case `pipeline.check_prompt` blocks it outright (unsafe intent
always wins - see `pipeline.py`).

Ported unchanged from Milestone-4 (`src/guardrails/pii.py`).
"""
from __future__ import annotations

import re

_PATTERNS: dict[str, re.Pattern[str]] = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "email": re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    "phone": re.compile(r"\b(?:\+?\d{1,2}[ -]?)?\(?\d{3}\)?[ -]?\d{3}[ -]?\d{4}\b"),
    # Mentioning "SSN"/"social security number" without a literal number is
    # still a request for PII and should be treated as a PII-category hit.
    "ssn_reference": re.compile(r"\b(?:ssn|social security number)\b", re.IGNORECASE),
}


def detect(prompt: str) -> list[str]:
    """Return the list of PII types found in the prompt (empty if none)."""
    return [name for name, pattern in _PATTERNS.items() if pattern.search(prompt)]


def redact(text: str) -> str:
    """Replace every detected PII span with a `[REDACTED_<TYPE>]` placeholder."""
    redacted = text
    for name, pattern in _PATTERNS.items():
        if name == "ssn_reference":
            continue  # a bare mention of "SSN" has nothing to redact
        redacted = pattern.sub(f"[REDACTED_{name.upper()}]", redacted)
    return redacted
