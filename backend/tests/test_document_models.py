from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app.models import (
    DEFAULT_ACTOR,
    Analysis,
    AuditEvent,
    AuditEventType,
    Document,
    DocumentDecision,
    DocumentExtraction,
    DocumentStatus,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

DOCUMENT_COLUMNS = {
    "id",
    "filename",
    "content_type",
    "size_bytes",
    "sha256",
    "status",
    "text",
    "received_at",
    "updated_at",
}
EXTRACTION_COLUMNS = {
    "id",
    "document_id",
    "provider",
    "model",
    "status",
    "fields",
    "warnings",
    "created_at",
}
DECISION_COLUMNS = {
    "id",
    "document_id",
    "extraction_id",
    "decision",
    "corrections",
    "reason",
    "actor",
    "decided_at",
}
AUDIT_COLUMNS = {"id", "document_id", "event_type", "actor", "data", "created_at"}


def _document() -> Document:
    return Document(
        filename="engagement.txt",
        content_type="text/plain",
        size_bytes=2048,
        sha256="a" * 64,
        text="Client: Acme Corp",
        received_at=NOW,
    )


def test_document_workflow_tables_and_columns_exist(db_engine):
    inspector = inspect(db_engine)
    tables = set(inspector.get_table_names())

    assert {
        "analyses",
        "documents",
        "document_extractions",
        "document_decisions",
        "audit_events",
    } <= tables

    assert {c["name"] for c in inspector.get_columns("documents")} == DOCUMENT_COLUMNS
    assert {c["name"] for c in inspector.get_columns("document_extractions")} == EXTRACTION_COLUMNS
    assert {c["name"] for c in inspector.get_columns("document_decisions")} == DECISION_COLUMNS
    assert {c["name"] for c in inspector.get_columns("audit_events")} == AUDIT_COLUMNS


def test_expected_indexes_are_created(db_engine):
    inspector = inspect(db_engine)

    assert {"ix_documents_sha256", "ix_documents_status"} <= {
        index["name"] for index in inspector.get_indexes("documents")
    }
    assert "ix_document_extractions_document_id" in {
        index["name"] for index in inspector.get_indexes("document_extractions")
    }
    assert {"ix_document_decisions_document_id", "ix_document_decisions_extraction_id"} <= {
        index["name"] for index in inspector.get_indexes("document_decisions")
    }
    assert "ix_audit_events_document_id" in {
        index["name"] for index in inspector.get_indexes("audit_events")
    }


def test_foreign_keys_reference_parent_tables_with_cascade(db_engine):
    inspector = inspect(db_engine)

    def fk_map(table):
        return {
            tuple(fk["constrained_columns"]): (fk["referred_table"], fk["options"].get("ondelete"))
            for fk in inspector.get_foreign_keys(table)
        }

    assert fk_map("document_extractions")[("document_id",)] == ("documents", "CASCADE")
    assert fk_map("document_decisions")[("document_id",)] == ("documents", "CASCADE")
    assert fk_map("document_decisions")[("extraction_id",)] == ("document_extractions", "CASCADE")
    assert fk_map("audit_events")[("document_id",)] == ("documents", "CASCADE")


def test_defaults_for_status_and_actor(db_engine):
    inspector = inspect(db_engine)

    def server_default(table, column):
        for col in inspector.get_columns(table):
            if col["name"] == column:
                return col["default"]
        raise AssertionError(f"{table}.{column} missing")

    assert "received" in server_default("documents", "status")
    assert "owner" in server_default("document_decisions", "actor")
    assert "owner" in server_default("audit_events", "actor")
    assert DEFAULT_ACTOR == "owner"


def test_status_and_audit_event_constants_match_contract():
    assert DocumentStatus.RECEIVED == "received"
    assert DocumentStatus.EXTRACTION_FAILED == "extraction_failed"
    assert {DocumentStatus.RECEIVED, DocumentStatus.APPROVED, DocumentStatus.REJECTED} <= {
        "received",
        "extracting",
        "extracted",
        "extraction_failed",
        "approved",
        "rejected",
    }
    assert AuditEventType.DOCUMENT_RECEIVED == "document_received"
    assert AuditEventType.DECISION_RECORDED == "decision_recorded"


def test_relationships_link_extractions_decisions_and_audit(db_session):
    document = _document()
    db_session.add(document)
    db_session.commit()

    extraction = DocumentExtraction(
        document_id=document.id,
        provider="deterministic",
        model=None,
        status="succeeded",
        fields=[{"name": "client_name", "value": "Acme", "confidence": 0.9}],
        warnings=[],
    )
    db_session.add(extraction)
    db_session.commit()

    decision = DocumentDecision(
        document_id=document.id,
        extraction_id=extraction.id,
        decision="approved",
        corrections=[],
        reason=None,
        actor=DEFAULT_ACTOR,
        decided_at=NOW,
    )
    audit = AuditEvent(
        document_id=document.id,
        event_type=AuditEventType.DOCUMENT_RECEIVED,
        actor=DEFAULT_ACTOR,
        data={"size_bytes": 2048},
    )
    db_session.add_all([decision, audit])
    db_session.commit()

    db_session.refresh(document)
    assert [e.id for e in document.extractions] == [extraction.id]
    assert [d.id for d in document.decisions] == [decision.id]
    assert [a.id for a in document.audit_events] == [audit.id]
    assert decision.extraction.id == extraction.id
    assert extraction.document.id == document.id
    assert document.extractions[0].fields[0]["name"] == "client_name"
    assert document.audit_events[0].data == {"size_bytes": 2048}


def test_deleting_document_cascades_to_children(db_session):
    document = _document()
    db_session.add(document)
    db_session.commit()

    extraction = DocumentExtraction(
        document_id=document.id,
        provider="deterministic",
        status="succeeded",
        fields=[],
        warnings=[],
    )
    db_session.add(extraction)
    db_session.commit()
    db_session.add_all(
        [
            DocumentDecision(
                document_id=document.id,
                extraction_id=extraction.id,
                decision="approved",
                corrections=[],
                decided_at=NOW,
            ),
            AuditEvent(
                document_id=document.id,
                event_type=AuditEventType.DOCUMENT_RECEIVED,
                data={},
            ),
        ]
    )
    db_session.commit()

    db_session.delete(document)
    db_session.commit()

    assert db_session.execute(select(Document)).scalars().all() == []
    assert db_session.execute(select(DocumentExtraction)).scalars().all() == []
    assert db_session.execute(select(DocumentDecision)).scalars().all() == []
    assert db_session.execute(select(AuditEvent)).scalars().all() == []


def test_required_columns_reject_missing_values(db_session):
    db_session.add(Document(content_type="text/plain", size_bytes=1, sha256="a", received_at=NOW))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(Document(filename="a.txt", size_bytes=1, sha256="a", received_at=NOW))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    document = _document()
    db_session.add(document)
    db_session.commit()
    db_session.add(AuditEvent(document_id=document.id, event_type="document_received"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_existing_analysis_model_is_intact(db_engine):
    inspector = inspect(db_engine)

    assert "analyses" in inspector.get_table_names()
    assert {"id", "owner", "repository", "analyzed_at", "summary", "metrics", "findings", "created_at"} == {
        column["name"] for column in inspector.get_columns("analyses")
    }
    assert Analysis.__tablename__ == "analyses"
