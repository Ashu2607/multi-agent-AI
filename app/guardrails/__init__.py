"""Guardrails package (M6): prompt-injection / jailbreak / PII / toxicity
detection, ported and strengthened from the Milestone-4 `src/guardrails`
package (`ashutosh_milestone4.zip`) rather than rebuilt from scratch.

`pipeline.check_prompt()` is the single entry point `app/api.py` calls
before a research request reaches the M3 LangGraph pipeline.
"""
from __future__ import annotations

from app.guardrails.pipeline import GuardrailDecision, check_prompt

__all__ = ["GuardrailDecision", "check_prompt"]
