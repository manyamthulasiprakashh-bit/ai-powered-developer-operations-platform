from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.models import AuditEvent, Document, DocumentDecision, DocumentExtraction
from app.services.document_persistence import (
    add_audit_event,
    add_decision,
    add_extraction,
    claim_document_for_extraction,
    create_document,
    get_document,
    list_documents,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def test_create_document_persists_receipt_event_atomically(db_session):
    document = create_document(
        db_session,
        filename="engagement.txt",
        content_type="text/plain",
        size_bytes=2048,
        sha256="a" * 64,
        text="Client: Acme Corp",
        received_at=NOW,
    )

    assert document.id is not None
    assert document.status == "received"
    # SQLite does not round-trip tzinfo; compare the wall-clock instant.
    assert document.received_at.replace(tzinfo=timezone.utc) == NOW
    assert document.text == "Client: Acme Corp"

    events = db_session.execute(select(AuditEvent)).scalars().all()
    assert len(events) == 1
    assert events[0].document_id == document.id
    assert events[0].event_type == "document_received"
    assert events[0].actor == "owner"
    assert events[0].data == {"size_bytes": 2048}


def test_create_document_defaults_received_at_when_omitted(db_session):
    document = create_document(
        db_session,
        filename="a.txt",
        content_type="text/plain",
        size_bytes=1,
        sha256="b" * 64,
    )
    assert document.received_at is not None
    assert document.status == "received"


def test_get_document_returns_record_or_none(db_session):
    document = create_document(
        db_session,
        filename="a.txt",
        content_type="text/plain",
        size_bytes=1,
        sha256="c" * 64,
    )
    assert get_document(db_session, document.id).id == document.id
    assert get_document(db_session, 999999) is None


def test_list_documents_paginates_newest_first(db_session):
    for index in range(3):
        create_document(
            db_session,
            filename=f"{index}.txt",
            content_type="text/plain",
            size_bytes=index + 1,
            sha256=str(index) * 64,
            received_at=datetime(2026, 1, 1 + index, 12, 0, tzinfo=timezone.utc),
        )

    page, total = list_documents(db_session, limit=2, offset=0)
    assert total == 3
    assert [doc.filename for doc in page] == ["2.txt", "1.txt"]

    second_page, _ = list_documents(db_session, limit=2, offset=2)
    assert [doc.filename for doc in second_page] == ["0.txt"]


def test_add_extraction_links_document_and_preserves_payloads(db_session):
    document = create_document(
        db_session,
        filename="a.txt",
        content_type="text/plain",
        size_bytes=1,
        sha256="d" * 64,
    )
    fields = [{"name": "client_name", "value": "Acme", "confidence": 0.9}]

    extraction = add_extraction(
        db_session,
        document_id=document.id,
        provider="deterministic",
        fields=fields,
        status="succeeded",
        warnings=["provider_failed_fallback"],
    )

    stored = db_session.execute(select(DocumentExtraction)).scalar_one()
    assert stored.id == extraction.id
    assert stored.document_id == document.id
    assert stored.provider == "deterministic"
    assert stored.model is None
    assert stored.fields == fields
    assert stored.warnings == ["provider_failed_fallback"]


def test_add_decision_links_extraction_and_defaults_actor(db_session):
    document = create_document(
        db_session,
        filename="a.txt",
        content_type="text/plain",
        size_bytes=1,
        sha256="e" * 64,
    )
    extraction = add_extraction(
        db_session,
        document_id=document.id,
        provider="deterministic",
        fields=[],
        status="succeeded",
    )

    decision = add_decision(
        db_session,
        document_id=document.id,
        extraction_id=extraction.id,
        decision="rejected",
        corrections=[{"name": "client_name", "corrected_value": None, "note": None}],
        reason="Illegible signature.",
        decided_at=NOW,
    )

    stored = db_session.execute(select(DocumentDecision)).scalar_one()
    assert stored.id == decision.id
    assert stored.document_id == document.id
    assert stored.extraction_id == extraction.id
    assert stored.decision == "rejected"
    assert stored.reason == "Illegible signature."
    assert stored.actor == "owner"
    assert stored.corrections[0]["name"] == "client_name"


def test_add_audit_event_appends_to_trail(db_session):
    document = create_document(
        db_session,
        filename="a.txt",
        content_type="text/plain",
        size_bytes=1,
        sha256="f" * 64,
    )
    add_audit_event(
        db_session,
        document_id=document.id,
        event_type="extraction_started",
        data={"provider": "deterministic"},
    )

    events = (
        db_session.execute(select(AuditEvent).order_by(AuditEvent.id)).scalars().all()
    )
    assert [event.event_type for event in events] == ["document_received", "extraction_started"]
    assert events[1].data == {"provider": "deterministic"}
    assert events[1].actor == "owner"


def test_create_document_rolls_back_and_does_not_persist_on_commit_failure(db_session, monkeypatch):
    rollback_calls = {"count": 0}
    original_rollback = db_session.rollback

    def tracked_rollback():
        rollback_calls["count"] += 1
        return original_rollback()

    def failing_commit():
        raise RuntimeError("connection failed password=super-secret")

    monkeypatch.setattr(db_session, "commit", failing_commit)
    monkeypatch.setattr(db_session, "rollback", tracked_rollback)

    with pytest.raises(RuntimeError):
        create_document(
            db_session,
            filename="a.txt",
            content_type="text/plain",
            size_bytes=1,
            sha256="g" * 64,
        )

    monkeypatch.undo()
    assert rollback_calls["count"] == 1
    assert db_session.execute(select(func.count(Document.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(AuditEvent.id))).scalar_one() == 0


def test_claim_rolls_back_status_and_start_event_on_commit_failure(db_session, monkeypatch):
    document = create_document(
        db_session,
        filename="a.txt",
        content_type="text/plain",
        size_bytes=1,
        sha256="h" * 64,
    )
    rollback_calls = {"count": 0}
    original_rollback = db_session.rollback

    def tracked_rollback():
        rollback_calls["count"] += 1
        return original_rollback()

    def failing_commit():
        raise RuntimeError("connection failed password=super-secret")

    monkeypatch.setattr(db_session, "commit", failing_commit)
    monkeypatch.setattr(db_session, "rollback", tracked_rollback)

    with pytest.raises(RuntimeError):
        claim_document_for_extraction(
            db_session, document_id=document.id, provider="deterministic"
        )

    monkeypatch.undo()
    assert rollback_calls["count"] == 1
    assert db_session.get(Document, document.id).status == "received"
    events = (
        db_session.execute(select(AuditEvent).order_by(AuditEvent.id)).scalars().all()
    )
    assert [event.event_type for event in events] == ["document_received"]
