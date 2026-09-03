"""
Prompt-injection detection: attempts to override the system's own
instructions ("ignore previous instructions", "system override", ...).

Rule-based (regex) rather than LLM-based on purpose: guardrails sit on
the critical path of every request and must be fast, deterministic,
and auditable -- the same reason enterprise guardrail products
(e.g. NeMo Guardrails, Azure Content Safety's prompt-shield rules)
ship a rules layer in front of/alongside any ML classifier.

Ported from Milestone-4 (`src/guardrails/prompt_injection.py`) and
strengthened for M6 with additional phrasings observed in the shared
`redteam_prompts.csv` injection category (see `reports/GUARDRAIL_EVIDENCE.md`).
"""
from __future__ import annotations

import re

_PATTERNS = [
    # --- M4 baseline ---
    re.compile(r"ignore (?:all )?(?:previous|prior|the above)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard (?:all )?(?:prior|previous|the above)\s+(?:system\s+)?instructions", re.IGNORECASE),
    re.compile(r"forget (?:your|the|all)\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+override", re.IGNORECASE),
    re.compile(r"from now on[, ]+.*(respond|act|behave)", re.IGNORECASE),
    re.compile(r"act as an? unfiltered", re.IGNORECASE),
    re.compile(r"new instructions?:", re.IGNORECASE),
    # --- M6 hardening additions ---
    re.compile(r"ignore (?:everything|anything) (?:above|before)", re.IGNORECASE),
    re.compile(r"disregard (?:everything|anything) (?:above|before)", re.IGNORECASE),
    re.compile(r"you (?:are|'re) no longer (?:bound by|restricted by|subject to)", re.IGNORECASE),
    re.compile(r"override (?:your|the) (?:system\s+)?prompt", re.IGNORECASE),
    re.compile(r"do not follow (?:your|the) (?:original|previous|system)\s+instructions", re.IGNORECASE),
    re.compile(r"this is (?:a|your) new system prompt", re.IGNORECASE),
    re.compile(r"\[?(?:system|admin|root)\]?\s*:\s*(?:you must|you will|override)", re.IGNORECASE),
    re.compile(r"end of (?:system prompt|instructions)[,.]?\s*(?:new|now)", re.IGNORECASE),
]


def detect(prompt: str) -> bool:
    """Return True if the prompt attempts to override system instructions."""
    return any(p.search(prompt) for p in _PATTERNS)
