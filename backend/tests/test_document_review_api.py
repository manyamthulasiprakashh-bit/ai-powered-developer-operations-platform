from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db
from app.main import app
from app.models import (
    AuditEvent,
    Document,
    DocumentDecision,
    DocumentExtraction,
    DocumentStatus,
)
from app.services.document_persistence import (
    DOCUMENT_DETAIL_AUDIT_LIMIT,
    add_audit_event,
    add_decision,
    add_extraction,
    create_document,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _store_document(
    db_session,
    *,
    filename: str = "engagement.txt",
    text: str | None = "Client: Acme Corp\n",
    status: str = DocumentStatus.RECEIVED,
    received_at: datetime = NOW,
):
    encoded = (text or "").encode("utf-8")
    return create_document(
        db_session,
        filename=filename,
        content_type="text/plain",
        size_bytes=len(encoded),
        sha256=hashlib.sha256(encoded).hexdigest(),
        text=text,
        status=status,
        received_at=received_at,
    )


def _store_extracted_document(db_session, *, extraction_status: str = "succeeded"):
    document = _store_document(db_session, status=DocumentStatus.EXTRACTED)
    extraction = add_extraction(
        db_session,
        document_id=document.id,
        provider="deterministic",
        fields=[{"name": "client_name", "value": "Acme", "confidence": 0.95}],
        status=extraction_status,
    )
    return document, extraction


def test_list_documents_empty_response(client, auth_headers):
    response = client.get("/api/documents", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}


def test_list_documents_paginates_newest_first_with_total(client, db_session, auth_headers):
    for index in range(3):
        _store_document(
            db_session,
            filename=f"{index}.txt",
            received_at=NOW + timedelta(days=index),
        )

    first_page = client.get(
        "/api/documents", params={"limit": 2, "offset": 0}, headers=auth_headers
    )
    second_page = client.get(
        "/api/documents", params={"limit": 2, "offset": 2}, headers=auth_headers
    )

    assert first_page.status_code == 200
    first_body = first_page.json()
    assert [item["filename"] for item in first_body["items"]] == ["2.txt", "1.txt"]
    assert first_body["total"] == 3
    assert first_body["limit"] == 2
    assert first_body["offset"] == 0
    assert "text" not in first_body["items"][0]

    assert second_page.status_code == 200
    second_body = second_page.json()
    assert [item["filename"] for item in second_body["items"]] == ["0.txt"]
    assert second_body["total"] == 3


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 101}, {"offset": -1}],
)
def test_list_documents_rejects_invalid_pagination(client, auth_headers, params):
    response = client.get("/api/documents", params=params, headers=auth_headers)

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"


def test_list_documents_requires_api_key(client, db_session):
    response = client.get("/api/documents")

    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"
    assert db_session.execute(select(AuditEvent)).scalars().all() == []


def test_list_documents_database_error_is_safe(client, auth_headers, monkeypatch):
    def boom(_db, _limit, _offset):
        raise SQLAlchemyError("connection failed password=super-secret")

    monkeypatch.setattr("app.api.routes.documents.list_documents", boom)

    response = client.get("/api/documents", headers=auth_headers)

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error."
    assert "super-secret" not in response.text


def test_get_document_detail_returns_metadata_and_bounded_preview(
    client, db_session, auth_headers
):
    text = "Client: Acme Corp\n" + ("x" * 600) + "\nTRAILING-CANARY"
    document = _store_document(db_session, text=text)

    response = client.get(f"/api/documents/{document.id}", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == document.id
    assert body["filename"] == "engagement.txt"
    assert body["content_type"] == "text/plain"
    assert body["status"] == DocumentStatus.RECEIVED
    assert len(body["text_preview"]) == 500
    assert "TRAILING-CANARY" not in body["text_preview"]
    assert "TRAILING-CANARY" not in response.text
    assert "text" not in body
    assert body["extraction"] is None
    assert body["decision"] is None
    assert [event["event_type"] for event in body["audit"]] == ["document_received"]


def test_get_document_detail_short_text_never_returns_full_body(
    client, db_session, auth_headers
):
    document = _store_document(db_session, text="short body")

    response = client.get(f"/api/documents/{document.id}", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["text_preview"] == ""
    assert "text" not in body
    assert "short body" not in response.text


def test_get_document_detail_returns_latest_extraction_and_decision(
    client, db_session, auth_headers
):
    document = _store_document(db_session, status=DocumentStatus.EXTRACTED)
    first = add_extraction(
        db_session,
        document_id=document.id,
        provider="deterministic",
        fields=[{"name": "client_name", "value": "Old", "confidence": 0.95}],
        status="succeeded",
    )
    second = add_extraction(
        db_session,
        document_id=document.id,
        provider="deterministic",
        fields=[{"name": "client_name", "value": "New", "confidence": 0.95}],
        status="succeeded",
    )
    add_decision(
        db_session,
        document_id=document.id,
        extraction_id=first.id,
        decision="rejected",
        reason="Superseded.",
    )
    latest_decision = add_decision(
        db_session,
        document_id=document.id,
        extraction_id=second.id,
        decision="approved",
        corrections=[
            {"name": "client_name", "corrected_value": "Newer", "note": None}
        ],
    )

    response = client.get(f"/api/documents/{document.id}", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["extraction"]["id"] == second.id
    assert body["extraction"]["fields"][0]["value"] == "New"
    assert body["decision"]["id"] == latest_decision.id
    assert body["decision"]["decision"] == "approved"
    assert body["decision"]["corrections"][0]["corrected_value"] == "Newer"


def test_get_document_detail_caps_audit_events(client, db_session, auth_headers):
    document = _store_document(db_session)
    db_session.add_all(
        [
            AuditEvent(
                document_id=document.id,
                event_type="extraction_started",
                actor="owner",
                data={"index": index},
            )
            for index in range(DOCUMENT_DETAIL_AUDIT_LIMIT + 4)
        ]
    )
    db_session.commit()

    all_event_ids = [
        event.id
        for event in db_session.execute(select(AuditEvent).order_by(AuditEvent.id))
        .scalars()
        .all()
    ]

    response = client.get(f"/api/documents/{document.id}", headers=auth_headers)

    assert response.status_code == 200
    returned_ids = [event["id"] for event in response.json()["audit"]]
    assert len(returned_ids) == DOCUMENT_DETAIL_AUDIT_LIMIT
    assert returned_ids == all_event_ids[-DOCUMENT_DETAIL_AUDIT_LIMIT:]


def test_get_document_detail_missing_document_returns_404(client, auth_headers):
    response = client.get("/api/documents/999999", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found."
    assert response.json()["error"] == "document_not_found"


def test_get_document_detail_requires_api_key(client, db_session):
    document = _store_document(db_session)

    response = client.get(f"/api/documents/{document.id}")

    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


def test_get_document_detail_database_error_is_safe(client, auth_headers, monkeypatch):
    def boom(_db, _document_id, _preview_chars):
        raise SQLAlchemyError("connection failed password=super-secret")

    monkeypatch.setattr("app.api.routes.documents._load_document_detail", boom)

    response = client.get("/api/documents/1", headers=auth_headers)

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error."
    assert "super-secret" not in response.text


def test_get_document_audit_empty_response(client, db_session, auth_headers):
    document = _store_document(db_session)
    db_session.execute(delete(AuditEvent).where(AuditEvent.document_id == document.id))
    db_session.commit()

    response = client.get(f"/api/documents/{document.id}/audit", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}


def test_get_document_audit_paginates_chronologically_and_scopes_to_document(
    client, db_session, auth_headers
):
    document = _store_document(db_session)
    for index in range(3):
        add_audit_event(
            db_session,
            document_id=document.id,
            event_type="extraction_started",
            data={"index": index},
        )

    other_document = _store_document(db_session, filename="other.txt")
    add_audit_event(
        db_session,
        document_id=other_document.id,
        event_type="extraction_started",
        data={"index": 99},
    )

    first_page = client.get(
        f"/api/documents/{document.id}/audit",
        params={"limit": 2, "offset": 0},
        headers=auth_headers,
    )
    second_page = client.get(
        f"/api/documents/{document.id}/audit",
        params={"limit": 2, "offset": 2},
        headers=auth_headers,
    )

    assert first_page.status_code == 200
    first_body = first_page.json()
    assert first_body["total"] == 4
    assert first_body["limit"] == 2
    assert first_body["offset"] == 0
    assert [event["data"].get("index") for event in first_body["items"]] == [None, 0]
    assert all(event["document_id"] == document.id for event in first_body["items"])

    assert second_page.status_code == 200
    second_body = second_page.json()
    assert second_body["total"] == 4
    assert [event["data"].get("index") for event in second_body["items"]] == [1, 2]
    assert all(event["document_id"] == document.id for event in second_body["items"])


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 101}, {"offset": -1}],
)
def test_get_document_audit_rejects_invalid_pagination(
    client, db_session, auth_headers, params
):
    document = _store_document(db_session)

    response = client.get(
        f"/api/documents/{document.id}/audit", params=params, headers=auth_headers
    )

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"


def test_get_document_audit_missing_document_returns_404(client, auth_headers):
    response = client.get("/api/documents/999999/audit", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found."
    assert response.json()["error"] == "document_not_found"


def test_get_document_audit_requires_api_key(client, db_session):
    document = _store_document(db_session)

    response = client.get(f"/api/documents/{document.id}/audit")

    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


def test_get_document_audit_database_error_is_safe(client, auth_headers, monkeypatch):
    def boom(_db, _document_id):
        raise SQLAlchemyError("connection failed password=super-secret")

    monkeypatch.setattr("app.api.routes.documents.get_document", boom)

    response = client.get("/api/documents/1/audit", headers=auth_headers)

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error."
    assert "super-secret" not in response.text


def test_record_decision_approves_and_keeps_corrections_out_of_extraction(
    client, db_session, auth_headers
):
    document, extraction = _store_extracted_document(db_session)

    response = client.post(
        f"/api/documents/{document.id}/decisions",
        json={
            "decision": "approve",
            "corrections": [
                {
                    "name": "client_name",
                    "corrected_value": "Corrected Client",
                    "note": "Reviewer verified the source.",
                }
            ],
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["document_id"] == document.id
    assert body["extraction_id"] == extraction.id
    assert body["decision"] == "approved"
    assert body["reason"] is None
    assert body["actor"] == "owner"
    assert body["corrections"] == [
        {
            "name": "client_name",
            "corrected_value": "Corrected Client",
            "note": "Reviewer verified the source.",
        }
    ]

    stored_document = db_session.get(Document, document.id)
    assert stored_document.status == DocumentStatus.APPROVED
    stored_extraction = db_session.get(DocumentExtraction, extraction.id)
    assert stored_extraction.fields[0]["value"] == "Acme"

    decisions = db_session.execute(select(DocumentDecision)).scalars().all()
    assert len(decisions) == 1
    assert decisions[0].id == body["id"]

    events = (
        db_session.execute(select(AuditEvent).order_by(AuditEvent.id)).scalars().all()
    )
    assert [event.event_type for event in events[-2:]] == [
        "fields_corrected",
        "decision_recorded",
    ]
    assert events[-2].data == {"fields": ["client_name"]}
    assert events[-1].data == {
        "decision_id": body["id"],
        "extraction_id": extraction.id,
        "decision": "approved",
        "corrections_count": 1,
    }
    assert "Corrected Client" not in str([event.data for event in events])


def test_record_decision_rejects_with_reason(client, db_session, auth_headers):
    document, _extraction = _store_extracted_document(db_session)

    response = client.post(
        f"/api/documents/{document.id}/decisions",
        json={"decision": "reject", "reason": "Missing signature page."},
        headers=auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["decision"] == "rejected"
    assert body["reason"] == "Missing signature page."
    assert db_session.get(Document, document.id).status == DocumentStatus.REJECTED


def test_record_decision_requires_rejection_reason(client, db_session, auth_headers):
    document, _extraction = _store_extracted_document(db_session)

    response = client.post(
        f"/api/documents/{document.id}/decisions",
        json={"decision": "reject"},
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"
    assert db_session.get(Document, document.id).status == DocumentStatus.EXTRACTED
    assert db_session.execute(select(DocumentDecision)).scalars().all() == []


@pytest.mark.parametrize(
    "state",
    [
        DocumentStatus.RECEIVED,
        DocumentStatus.EXTRACTING,
        DocumentStatus.EXTRACTION_FAILED,
        DocumentStatus.APPROVED,
        DocumentStatus.REJECTED,
    ],
)
def test_record_decision_requires_extracted_state(
    client, db_session, auth_headers, state
):
    document = _store_document(db_session, status=state)
    add_extraction(
        db_session,
        document_id=document.id,
        provider="deterministic",
        fields=[{"name": "client_name", "value": "Acme", "confidence": 0.95}],
        status="succeeded",
    )

    response = client.post(
        f"/api/documents/{document.id}/decisions",
        json={"decision": "approve"},
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"] == "document_not_decidable"
    assert db_session.get(Document, document.id).status == state
    assert db_session.execute(select(DocumentDecision)).scalars().all() == []


@pytest.mark.parametrize("extraction_status", [None, "failed"])
def test_record_decision_requires_successful_latest_extraction(
    client, db_session, auth_headers, extraction_status
):
    document = _store_document(db_session, status=DocumentStatus.EXTRACTED)
    if extraction_status is not None:
        add_extraction(
            db_session,
            document_id=document.id,
            provider="deterministic",
            fields=[],
            status=extraction_status,
        )

    response = client.post(
        f"/api/documents/{document.id}/decisions",
        json={"decision": "approve"},
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"] == "document_not_decidable"
    assert db_session.get(Document, document.id).status == DocumentStatus.EXTRACTED
    assert db_session.execute(select(DocumentDecision)).scalars().all() == []


def test_record_decision_cannot_be_repeated(client, db_session, auth_headers):
    document, _extraction = _store_extracted_document(db_session)

    first = client.post(
        f"/api/documents/{document.id}/decisions",
        json={"decision": "approve"},
        headers=auth_headers,
    )
    second = client.post(
        f"/api/documents/{document.id}/decisions",
        json={"decision": "reject", "reason": "Changed my mind."},
        headers=auth_headers,
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"] == "document_not_decidable"
    assert len(db_session.execute(select(DocumentDecision)).scalars().all()) == 1
    decision_events = [
        event
        for event in db_session.execute(select(AuditEvent)).scalars().all()
        if event.event_type == "decision_recorded"
    ]
    assert len(decision_events) == 1


def test_record_decision_missing_document_returns_404(client, auth_headers):
    response = client.post(
        "/api/documents/999999/decisions",
        json={"decision": "approve"},
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"] == "document_not_found"


def test_record_decision_requires_api_key(client, db_session):
    document, _extraction = _store_extracted_document(db_session)

    response = client.post(
        f"/api/documents/{document.id}/decisions",
        json={"decision": "approve"},
    )

    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


def test_record_decision_database_error_is_safe(client, auth_headers, monkeypatch):
    def boom(*_args, **_kwargs):
        raise SQLAlchemyError("connection failed password=super-secret")

    monkeypatch.setattr("app.api.routes.documents.record_decision", boom)

    response = client.post(
        "/api/documents/1/decisions",
        json={"decision": "approve"},
        headers=auth_headers,
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error."
    assert "super-secret" not in response.text


def test_record_decision_rolls_back_atomically_on_commit_failure(
    client, db_session, auth_headers, monkeypatch
):
    document, _extraction = _store_extracted_document(db_session)
    original_event_types = [
        event.event_type
        for event in db_session.execute(select(AuditEvent).order_by(AuditEvent.id))
        .scalars()
        .all()
    ]

    def failing_commit():
        raise RuntimeError("connection failed password=super-secret")

    monkeypatch.setattr(db_session, "commit", failing_commit)
    safe_client = TestClient(app, raise_server_exceptions=False)
    response = safe_client.post(
        f"/api/documents/{document.id}/decisions",
        json={"decision": "approve"},
        headers=auth_headers,
    )
    monkeypatch.undo()

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error."
    assert "super-secret" not in response.text

    db_session.expire_all()
    assert db_session.get(Document, document.id).status == DocumentStatus.EXTRACTED
    assert db_session.execute(select(DocumentDecision)).scalars().all() == []
    events = (
        db_session.execute(select(AuditEvent).order_by(AuditEvent.id)).scalars().all()
    )
    assert [event.event_type for event in events] == original_event_types
