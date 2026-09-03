"""Report Writer Tool: compiles Researcher findings into an executive-ready
competitor analysis report, and screens it for sensitive data before it can
be routed to the human approval gate (Policy 1 + Policy 2).
"""
from __future__ import annotations

import re
from pathlib import Path

from app.config import REPORTS_DIR
from app.schemas import ReportDraft

_SENSITIVE_PATTERNS = [
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # SSN-like
    re.compile(r"\b(?:\d[ -]*?){13,16}\b"),  # credit-card-like digit runs
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),  # email addresses
]


def contains_sensitive_data(text: str) -> bool:
    return any(pattern.search(text) for pattern in _SENSITIVE_PATTERNS)


def render_markdown(draft: ReportDraft) -> str:
    lines = [f"# {draft.title}", "", "## Executive Summary", draft.executive_summary, ""]
    for section in draft.sections:
        lines.append(f"## {section.heading}")
        lines.append(section.content)
        lines.append("")
    if draft.sources:
        lines.append("## Sources")
        lines.extend(f"- {source}" for source in draft.sources)
        lines.append("")
    if draft.contains_sensitive_data:
        lines.insert(0, "> **WARNING: possible sensitive data detected - review before distribution.**\n")
    return "\n".join(lines)


def save_report(draft: ReportDraft, session_id: str) -> Path:
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"{session_id}_{draft.generated_at.strftime('%Y%m%dT%H%M%S')}.md"
    path.write_text(render_markdown(draft), encoding="utf-8")
    return path


def finalize_draft(draft: ReportDraft) -> ReportDraft:
    """Runs the sensitive-data screen (Policy 2) and flags the draft."""
    full_text = draft.executive_summary + "\n" + "\n".join(s.content for s in draft.sections)
    draft.contains_sensitive_data = contains_sensitive_data(full_text)
    return draft
