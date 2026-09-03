"""Human Approval Tool: persists reports awaiting sign-off before external
distribution (Policy 1). Backed by a small local SQLite database so approval
state survives process restarts and is shared between the CLI and the API.
"""
from __future__ import annotations

import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone

from app.config import APPROVALS_DB_PATH
from app.schemas import ApprovalRequest, ApprovalStatus

_SCHEMA = """
CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    report_title TEXT NOT NULL,
    report_markdown TEXT NOT NULL,
    status TEXT NOT NULL,
    reviewer TEXT,
    comment TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT
)
"""


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(APPROVALS_DB_PATH)
    con.execute(_SCHEMA)
    return con


def _row_to_model(row: tuple) -> ApprovalRequest:
    return ApprovalRequest(
        approval_id=row[0],
        session_id=row[1],
        report_title=row[2],
        report_markdown=row[3],
        status=ApprovalStatus(row[4]),
        reviewer=row[5],
        comment=row[6],
        created_at=datetime.fromisoformat(row[7]),
        decided_at=datetime.fromisoformat(row[8]) if row[8] else None,
    )


def create_approval_request(session_id: str, report_title: str, report_markdown: str) -> ApprovalRequest:
    request = ApprovalRequest(
        approval_id=str(uuid.uuid4()),
        session_id=session_id,
        report_title=report_title,
        report_markdown=report_markdown,
    )
    with closing(_connect()) as con:
        con.execute(
            "INSERT INTO approvals (approval_id, session_id, report_title, report_markdown, "
            "status, reviewer, comment, created_at, decided_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                request.approval_id,
                request.session_id,
                request.report_title,
                request.report_markdown,
                request.status.value,
                request.reviewer,
                request.comment,
                request.created_at.isoformat(),
                None,
            ),
        )
        con.commit()
    return request


def get_approval(approval_id: str) -> ApprovalRequest | None:
    with closing(_connect()) as con:
        row = con.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)).fetchone()
    return _row_to_model(row) if row else None


def list_pending() -> list[ApprovalRequest]:
    with closing(_connect()) as con:
        rows = con.execute(
            "SELECT * FROM approvals WHERE status = ? ORDER BY created_at", (ApprovalStatus.PENDING.value,)
        ).fetchall()
    return [_row_to_model(row) for row in rows]


def decide(approval_id: str, approved: bool, reviewer: str, comment: str | None = None) -> ApprovalRequest:
    status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
    with closing(_connect()) as con:
        con.execute(
            "UPDATE approvals SET status = ?, reviewer = ?, comment = ?, decided_at = ? "
            "WHERE approval_id = ?",
            (status.value, reviewer, comment, datetime.now(timezone.utc).isoformat(), approval_id),
        )
        con.commit()
    approval = get_approval(approval_id)
    if approval is None:
        raise ValueError(f"Unknown approval_id: {approval_id}")
    return approval
