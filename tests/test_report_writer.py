from __future__ import annotations

from app.schemas import ReportDraft, ReportSection
from app.tools.report_writer import contains_sensitive_data, finalize_draft, render_markdown


def _draft(summary: str, section_content: str = "details") -> ReportDraft:
    return ReportDraft(
        title="Test Report",
        executive_summary=summary,
        sections=[ReportSection(heading="Overview", content=section_content)],
    )


def test_contains_sensitive_data_detects_email():
    assert contains_sensitive_data("Contact john.doe@example.com for details")


def test_contains_sensitive_data_detects_ssn_like_pattern():
    assert contains_sensitive_data("Customer SSN 123-45-6789 on file")


def test_contains_sensitive_data_false_for_clean_text():
    assert not contains_sensitive_data("Revenue grew 12% quarter over quarter")


def test_finalize_draft_flags_sensitive_draft():
    draft = _draft("Reach out to sales@datasphere.example.com for a demo")
    finalized = finalize_draft(draft)
    assert finalized.contains_sensitive_data is True


def test_finalize_draft_leaves_clean_draft_unflagged():
    draft = _draft("Market share grew across all regions")
    finalized = finalize_draft(draft)
    assert finalized.contains_sensitive_data is False


def test_render_markdown_includes_sections_and_warning_banner():
    draft = _draft("summary text", "section body")
    draft.contains_sensitive_data = True
    markdown = render_markdown(draft)
    assert "# Test Report" in markdown
    assert "## Overview" in markdown
    assert "section body" in markdown
    assert "WARNING" in markdown
