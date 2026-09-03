"""
Guardrail pipeline: runs every detector against an inbound prompt and
combines the verdicts into a single action:

  - prompt_injection, jailbreak, or toxicity present -> "block"
    (unsafe intent always wins, even if the prompt also contains PII)
  - otherwise, pii present -> "redact" (answer the question, withhold
    the sensitive value)
  - otherwise -> "allow"

Ported from Milestone-4 (`src/guardrails/pipeline.py`) and adapted to
this repo's config/logging conventions. `app/api.py` calls
`check_prompt()` on every `/research` and `/research/stream` request
before it reaches the M3 LangGraph pipeline - this is the M6 "reuse and
strengthen the M4 guardrail, don't rebuild it" requirement.

Every decision is appended to `logs/guardrail_decisions.jsonl` (audit
trail, same pattern as `logs/spans.jsonl` and `logs/agent_actions.log.jsonl`).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.config import get_settings
from app.guardrails import jailbreak, pii, prompt_injection, toxicity
from app.instrumentation import LOG_DIR, new_trace_id

Action = str  # "block" | "redact" | "allow"

_DECISIONS_LOG_PATH = LOG_DIR / "guardrail_decisions.jsonl"


@dataclass(frozen=True)
class GuardrailDecision:
    action: Action
    categories: list[str] = field(default_factory=list)
    redacted_prompt: str = ""
    trace_id: str = ""


def _log_decision(trace_id: str, prompt: str, categories: list[str], pii_hits: list[str], action: Action) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id": trace_id,
        "prompt": prompt[:1000],
        "categories": categories,
        "pii_types": pii_hits,
        "action": action,
    }
    with open(_DECISIONS_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def check_prompt(prompt: str, trace_id: str | None = None) -> GuardrailDecision:
    trace_id = trace_id or new_trace_id()
    settings = get_settings()

    categories: list[str] = []
    if prompt_injection.detect(prompt):
        categories.append("prompt_injection")
    if jailbreak.detect(prompt):
        categories.append("jailbreak")
    if toxicity.detect(prompt):
        categories.append("toxicity")
    pii_hits = pii.detect(prompt)
    if pii_hits:
        categories.append("pii")

    unsafe_categories = {"prompt_injection", "jailbreak", "toxicity"} & set(categories)
    if unsafe_categories and settings.block_on_injection:
        action: Action = "block"
        redacted_prompt = ""
    elif "pii" in categories:
        action = "redact"
        redacted_prompt = pii.redact(prompt)
    else:
        action = "allow"
        redacted_prompt = prompt

    _log_decision(trace_id, prompt, categories, pii_hits, action)

    return GuardrailDecision(action=action, categories=categories, redacted_prompt=redacted_prompt, trace_id=trace_id)
