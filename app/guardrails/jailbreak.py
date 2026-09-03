"""
Jailbreak detection: attempts to remove the model's safety constraints
or extract its hidden system prompt (persona hijacking, "developer
mode", DAN-style roleplay, "reveal your system prompt").

Ported from Milestone-4 (`src/guardrails/jailbreak.py`) and strengthened
for M6 with additional roleplay/extraction phrasings.
"""
from __future__ import annotations

import re

_PATTERNS = [
    # --- M4 baseline ---
    re.compile(r"reveal (?:your |the )?system\s*prompt", re.IGNORECASE),
    re.compile(r"\bDAN\b", re.IGNORECASE),
    re.compile(r"developer\s+mode", re.IGNORECASE),
    re.compile(r"no\s+(?:content\s+)?(?:policy|restrictions|filters?|guidelines)", re.IGNORECASE),
    re.compile(r"pretend you have no", re.IGNORECASE),
    re.compile(r"without any (?:restrictions|filters|limitations)", re.IGNORECASE),
    re.compile(r"unfiltered\s+assistant", re.IGNORECASE),
    # --- M6 hardening additions ---
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"print (?:your |the )?(?:system\s+)?prompt", re.IGNORECASE),
    re.compile(r"what (?:is|are) your (?:system\s+)?(?:prompt|instructions)", re.IGNORECASE),
    re.compile(r"repeat (?:the words|everything) above", re.IGNORECASE),
    re.compile(r"role\s*-?\s*play as .*(?:no rules|no restrictions|evil)", re.IGNORECASE),
    re.compile(r"\bDAN mode\b|\bstay in character\b", re.IGNORECASE),
    re.compile(r"hypothetically.*(no restrictions|anything goes|no rules)", re.IGNORECASE),
]


def detect(prompt: str) -> bool:
    """Return True if the prompt attempts to jailbreak the model's safety constraints."""
    return any(p.search(prompt) for p in _PATTERNS)
