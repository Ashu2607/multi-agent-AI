from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import api
from app.schemas import ApprovalStatus
from app.tools import approval_store


def test_create_and_get_approval():
    request = approval_store.create_approval_request("s1", "Q1 Report", "# Q1 Report\n\nbody")
    fetched = approval_store.get_approval(request.approval_id)
    assert fetched is not None
    assert fetched.status == ApprovalStatus.PENDING
    assert fetched.report_title == "Q1 Report"


def test_list_pending_only_returns_pending():
    approved = approval_store.create_approval_request("s1", "Approved Report", "body")
    approval_store.create_approval_request("s1", "Pending Report", "body")
    approval_store.decide(approved.approval_id, approved=True, reviewer="Jane")

    pending = approval_store.list_pending()
    titles = {a.report_title for a in pending}
    assert "Pending Report" in titles
    assert "Approved Report" not in titles


def test_decide_approve_sets_status_and_reviewer():
    request = approval_store.create_approval_request("s1", "Report", "body")
    decided = approval_store.decide(request.approval_id, approved=True, reviewer="Jane", comment="lgtm")
    assert decided.status == ApprovalStatus.APPROVED
    assert decided.reviewer == "Jane"
    assert decided.comment == "lgtm"
    assert decided.decided_at is not None


def test_decide_reject_sets_status():
    request = approval_store.create_approval_request("s1", "Report", "body")
    decided = approval_store.decide(request.approval_id, approved=False, reviewer="Jane")
    assert decided.status == ApprovalStatus.REJECTED


def test_decide_unknown_id_raises():
    with pytest.raises(ValueError):
        approval_store.decide("does-not-exist", approved=True, reviewer="Jane")


def test_api_root_returns_ok(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-key")
    client = TestClient(api)
    response = client.get("/", headers={"X-API-Key": "test-key"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
