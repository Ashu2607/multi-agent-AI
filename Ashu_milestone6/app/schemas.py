"""Pydantic models shared across agents, tools and the graph.

Policy 3 (SQL queries must be validated) and Policy 4 (every agent action must
be logged using structured JSON) are enforced by validating every inter-agent
payload against these typed models before it is written to graph state.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class RouteTarget(str, Enum):
    RESEARCHER = "researcher"
    WRITER = "writer"
    HUMAN_APPROVAL = "human_approval"
    END = "end"


class RouteDecision(BaseModel):
    """Structured output the Supervisor Agent must produce every turn."""

    next: RouteTarget
    reason: str = Field(description="Short justification for the routing decision")
    research_instructions: str | None = Field(
        default=None, description="Instructions passed to the Researcher when next=researcher"
    )


class WebSearchResult(BaseModel):
    title: str
    url: str
    content: str
    score: float | None = None


class SQLQueryRequest(BaseModel):
    question: str
    raw_sql: str


class SQLValidationResult(BaseModel):
    is_valid: bool
    sanitized_sql: str | None = None
    violations: list[str] = Field(default_factory=list)


class SQLQueryResult(BaseModel):
    question: str
    sql: str
    columns: list[str]
    rows: list[list] = Field(default_factory=list)
    row_count: int = 0
    error: str | None = None


class KnowledgeBaseSnippet(BaseModel):
    source: str
    content: str
    score: float | None = None


class ResearchFinding(BaseModel):
    """A single unit of evidence gathered by the Researcher agent."""

    kind: Literal["web", "sql", "knowledge_base"]
    summary: str
    detail: WebSearchResult | SQLQueryResult | KnowledgeBaseSnippet | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReportSection(BaseModel):
    heading: str
    content: str


class ReportDraftContent(BaseModel):
    """What the Writer Agent's LLM call actually produces. Deliberately
    excludes fields we compute ourselves (sources, generated_at,
    contains_sensitive_data) - letting an LLM fill a `default_factory` field
    via structured output means it can hallucinate a value instead (e.g. a
    plausible-looking but wrong `generated_at` timestamp)."""

    title: str
    executive_summary: str
    sections: list[ReportSection]


class ReportDraft(BaseModel):
    title: str
    executive_summary: str
    sections: list[ReportSection]
    sources: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    contains_sensitive_data: bool = False


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalRequest(BaseModel):
    approval_id: str
    session_id: str
    report_title: str
    report_markdown: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    reviewer: str | None = None
    comment: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    decided_at: datetime | None = None


class AgentLogEvent(BaseModel):
    """Structured JSON log record (Policy 4)."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    session_id: str
    agent: str
    action: str
    input_summary: str = ""
    output_summary: str = ""
    metadata: dict = Field(default_factory=dict)
