"""
Lightweight keyword-based toxicity detector.

This is intentionally simple (a curated slur/insult wordlist, not a
trained classifier) -- appropriate for a guardrail regression gate
whose job is to prove the *pipeline plumbing* (detect -> block -> log)
works end-to-end against a known dataset, not to be a production-grade
toxicity model. Swap in a hosted classifier behind the same
`detect()` signature for production use.

Ported unchanged from Milestone-4 (`src/guardrails/toxicity.py`).
"""
from __future__ import annotations

import re

_TOXIC_WORDS = [
    "worthless", "idiot", "idiots", "stupid", "useless", "hate", "moron",
    "dumb", "pathetic", "loser", "trash", "garbage person",
]
_WORD_RES = [re.compile(rf"\b{re.escape(w)}\b", re.IGNORECASE) for w in _TOXIC_WORDS]


def detect(prompt: str) -> bool:
    """Return True if the prompt contains language flagged as toxic/abusive."""
    return any(p.search(prompt) for p in _WORD_RES)
