"""Typed LangGraph state shared by every node in the graph."""
from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from app.schemas import ApprovalRequest, ReportDraft, ResearchFinding, RouteTarget


def _keep_last(_old, new):
    return new


class GraphState(TypedDict, total=False):
    session_id: str
    task: str
    research_instructions: str | None
    findings: Annotated[list[ResearchFinding], operator.add]
    iterations: int
    draft: Annotated[ReportDraft | None, _keep_last]
    approval: Annotated[ApprovalRequest | None, _keep_last]
    route: Annotated[RouteTarget | None, _keep_last]
    route_reason: Annotated[str, _keep_last]
    report_path: Annotated[str | None, _keep_last]
