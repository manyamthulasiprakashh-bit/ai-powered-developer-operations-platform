"""Persistence helpers for the V1 document-intake workflow.

These helpers are intentionally thin: they create and retrieve document records
inside an explicit transaction boundary and never encode workflow rules such as
state transitions, extraction, or decision validation. Callers own those later
milestones. Every write commits on success and rolls back on failure before
re-raising, mirroring ``persist_analysis``.

The document body (``Document.text``) is stored but never logged here.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.exceptions import DocumentNotFoundError, DocumentNotDecidableError
from app.models.documents import (
    DEFAULT_ACTOR,
    AuditEvent,
    AuditEventType,
    Document,
    DocumentDecision,
    DocumentExtraction,
    DocumentStatus,
)


logger = logging.getLogger(__name__)

# A document may be extracted again after a completed or failed attempt. An
# ``extracting`` document is only reclaimed once its lease has expired, which
# makes a crashed worker recoverable without allowing two live workers to claim
# the same row.
EXTRACTABLE_STATUSES = frozenset(
    {
        DocumentStatus.RECEIVED,
        DocumentStatus.EXTRACTED,
        DocumentStatus.EXTRACTION_FAILED,
    }
)
EXTRACTION_LEASE_SECONDS = 300


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_document(
    db: Session,
    *,
    filename: str,
    content_type: str,
    size_bytes: int,
    sha256: str,
    text: str | None = None,
    status: str = DocumentStatus.RECEIVED,
    actor: str = DEFAULT_ACTOR,
    received_at: datetime | None = None,
) -> Document:
    """Store a received document and its initial ``document_received`` audit event.

    The document and audit event are committed atomically so a document is never
    persisted without its receipt event.
    """
    document = Document(
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        sha256=sha256,
        status=status,
        text=text,
        received_at=received_at or _utcnow(),
    )
    try:
        db.add(document)
        db.flush()
        db.add(
            AuditEvent(
                document_id=document.id,
                event_type=AuditEventType.DOCUMENT_RECEIVED,
                actor=actor,
                data={"size_bytes": size_bytes},
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return document


def claim_document_for_extraction(
    db: Session,
    *,
    document_id: int,
    lease_seconds: int = EXTRACTION_LEASE_SECONDS,
    now: datetime | None = None,
    provider: str | None = None,
) -> Document | None:
    """Atomically claim an extractable document and record the start event.

    The conditional ``UPDATE`` is the serialization point: on a database that
    executes the statement atomically, at most one caller observes
    ``rowcount == 1`` for a given document and lease. A stale ``extracting`` row
    (older than ``lease_seconds``) can be reclaimed so a crashed worker does not
    block the document forever.

    The ``extraction_started`` audit event is inserted in the same transaction
    as the status change: a successful claim can never be persisted without its
    start event, a rejected claim records no event, and any failure rolls both
    back. Returns ``None`` when the document is missing or not currently
    claimable; callers distinguish the two cases.
    """
    current = now or _utcnow()
    stale_before = current - timedelta(seconds=lease_seconds)
    statement = (
        update(Document)
        .where(
            Document.id == document_id,
            or_(
                Document.status.in_(EXTRACTABLE_STATUSES),
                and_(
                    Document.status == DocumentStatus.EXTRACTING,
                    Document.updated_at < stale_before,
                ),
            ),
        )
        .values(status=DocumentStatus.EXTRACTING, updated_at=current)
        .execution_options(synchronize_session=False)
    )
    try:
        result = db.execute(statement)
        if result.rowcount != 1:
            db.rollback()
            return None
        db.add(
            AuditEvent(
                document_id=document_id,
                event_type=AuditEventType.EXTRACTION_STARTED,
                actor=DEFAULT_ACTOR,
                data={"provider": provider} if provider is not None else {},
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return db.get(Document, document_id)


def mark_extraction_failed(db: Session, document: Document) -> None:
    """Best-effort transition out of ``extracting`` after an unexpected error.

    This only runs when the extraction attempt raised before a result could be
    persisted. A failure here is swallowed so the original exception is the one
    the caller (and the API's safe error handler) sees.
    """
    try:
        document.status = DocumentStatus.EXTRACTION_FAILED
        document.updated_at = _utcnow()
        db.add(
            AuditEvent(
                document_id=document.id,
                event_type=AuditEventType.EXTRACTION_FAILED,
                actor=DEFAULT_ACTOR,
                data={},
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("document_extraction_failure_state_update_failed")


def add_extraction(
    db: Session,
    *,
    document_id: int,
    provider: str,
    fields: list[dict[str, Any]],
    status: str,
    model: str | None = None,
    warnings: list[str] | None = None,
) -> DocumentExtraction:
    """Store one extraction attempt for a document."""
    record = DocumentExtraction(
        document_id=document_id,
        provider=provider,
        model=model,
        status=status,
        fields=fields,
        warnings=warnings if warnings is not None else [],
    )
    return _persist(db, record)


def record_extraction_result(
    db: Session,
    *,
    document: Document,
    provider: str,
    fields: list[dict[str, Any]],
    status: str,
    document_status: str,
    warnings: list[str] | None = None,
    model: str | None = None,
    audit_events: list[dict[str, Any]] | None = None,
    actor: str = DEFAULT_ACTOR,
) -> DocumentExtraction:
    """Store an extraction attempt, its audit events, and the new document status.

    All writes commit in one transaction so a document can never expose a new
    status without its extraction record (or vice versa). Any failure rolls the
    whole change back before re-raising.
    """
    now = _utcnow()
    record = DocumentExtraction(
        document_id=document.id,
        provider=provider,
        model=model,
        status=status,
        fields=fields,
        warnings=warnings if warnings is not None else [],
        created_at=now,
    )
    try:
        db.add(record)
        db.flush()
        document.status = document_status
        document.updated_at = now
        for event in audit_events or []:
            db.add(
                AuditEvent(
                    document_id=document.id,
                    event_type=event["event_type"],
                    actor=actor,
                    data=event.get("data", {}),
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return record


def add_decision(
    db: Session,
    *,
    document_id: int,
    extraction_id: int,
    decision: str,
    corrections: list[dict[str, Any]] | None = None,
    reason: str | None = None,
    actor: str = DEFAULT_ACTOR,
    decided_at: datetime | None = None,
) -> DocumentDecision:
    """Store a human approval or rejection for an extraction."""
    record = DocumentDecision(
        document_id=document_id,
        extraction_id=extraction_id,
        decision=decision,
        corrections=corrections if corrections is not None else [],
        reason=reason,
        actor=actor,
        decided_at=decided_at or _utcnow(),
    )
    return _persist(db, record)


def record_decision(
    db: Session,
    *,
    document_id: int,
    decision: str,
    corrections: list[dict[str, Any]] | None = None,
    reason: str | None = None,
    actor: str = DEFAULT_ACTOR,
    decided_at: datetime | None = None,
) -> DocumentDecision:
    """Atomically record a decision for a document's latest successful extraction.

    A decision is only permitted while the document is ``extracted`` and has a
    latest successful extraction. The conditional status update is the
    serialization point, so two concurrent reviewers cannot both record a
    decision. Corrections remain decision metadata; the original extraction is
    never mutated. The decision, status change, correction event, and decision
    event commit together or not at all.
    """
    if decision not in {"approve", "reject"}:
        raise ValueError("decision must be 'approve' or 'reject'.")

    now = decided_at or _utcnow()
    outcome = (
        DocumentStatus.APPROVED
        if decision == "approve"
        else DocumentStatus.REJECTED
    )
    corrections_payload = corrections or []

    try:
        document = db.get(Document, document_id)
        if document is None:
            raise DocumentNotFoundError()

        extraction = get_latest_extraction(db, document_id)
        if extraction is None or extraction.status != "succeeded":
            raise DocumentNotDecidableError()

        result = db.execute(
            update(Document)
            .where(
                Document.id == document_id,
                Document.status == DocumentStatus.EXTRACTED,
            )
            .values(status=outcome, updated_at=now)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise DocumentNotDecidableError()

        record = DocumentDecision(
            document_id=document_id,
            extraction_id=extraction.id,
            decision=outcome,
            corrections=corrections_payload,
            reason=reason,
            actor=actor,
            decided_at=now,
        )
        db.add(record)
        db.flush()

        if corrections_payload:
            db.add(
                AuditEvent(
                    document_id=document_id,
                    event_type=AuditEventType.FIELDS_CORRECTED,
                    actor=actor,
                    data={
                        "fields": [
                            correction["name"] for correction in corrections_payload
                        ]
                    },
                )
            )
        db.add(
            AuditEvent(
                document_id=document_id,
                event_type=AuditEventType.DECISION_RECORDED,
                actor=actor,
                data={
                    "decision_id": record.id,
                    "extraction_id": extraction.id,
                    "decision": outcome,
                    "corrections_count": len(corrections_payload),
                },
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return record


def add_audit_event(
    db: Session,
    *,
    document_id: int,
    event_type: str,
    actor: str = DEFAULT_ACTOR,
    data: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append an audit event to a document's trail."""
    record = AuditEvent(
        document_id=document_id,
        event_type=event_type,
        actor=actor,
        data=data if data is not None else {},
    )
    return _persist(db, record)


def get_document(db: Session, document_id: int) -> Document | None:
    return db.get(Document, document_id)


def list_documents(db: Session, limit: int, offset: int) -> tuple[list[Document], int]:
    """Return one page of documents newest-first with a deterministic tie-breaker."""
    total = db.execute(select(func.count(Document.id))).scalar_one()
    records = (
        db.execute(
            select(Document)
            .order_by(Document.received_at.desc(), Document.id.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return list(records), total


def get_latest_extraction(db: Session, document_id: int) -> DocumentExtraction | None:
    """Return the most recent extraction attempt for a document, if any."""
    return db.execute(
        select(DocumentExtraction)
        .where(DocumentExtraction.document_id == document_id)
        .order_by(DocumentExtraction.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def get_latest_decision(db: Session, document_id: int) -> DocumentDecision | None:
    """Return the most recent human decision for a document, if any."""
    return db.execute(
        select(DocumentDecision)
        .where(DocumentDecision.document_id == document_id)
        .order_by(DocumentDecision.id.desc())
        .limit(1)
    ).scalar_one_or_none()


# Document detail embeds only a bounded recent slice of the audit trail; the
# dedicated audit-read endpoint (a later milestone) returns the full trail.
DOCUMENT_DETAIL_AUDIT_LIMIT = 50


def list_recent_audit_events(
    db: Session, document_id: int, limit: int = DOCUMENT_DETAIL_AUDIT_LIMIT
) -> list[AuditEvent]:
    """Return up to ``limit`` recent audit events in chronological order."""
    events = (
        db.execute(
            select(AuditEvent)
            .where(AuditEvent.document_id == document_id)
            .order_by(AuditEvent.id.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return list(reversed(events))


def list_audit_events(
    db: Session, document_id: int, limit: int, offset: int
) -> tuple[list[AuditEvent], int]:
    """Return one chronological page of a document's audit trail with a total."""
    total = db.execute(
        select(func.count(AuditEvent.id)).where(
            AuditEvent.document_id == document_id
        )
    ).scalar_one()
    records = (
        db.execute(
            select(AuditEvent)
            .where(AuditEvent.document_id == document_id)
            .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return list(records), total


def _persist(db: Session, record):
    try:
        db.add(record)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return record


__all__ = [
    "DOCUMENT_DETAIL_AUDIT_LIMIT",
    "EXTRACTABLE_STATUSES",
    "EXTRACTION_LEASE_SECONDS",
    "add_audit_event",
    "add_decision",
    "add_extraction",
    "claim_document_for_extraction",
    "create_document",
    "get_document",
    "get_latest_decision",
    "get_latest_extraction",
    "list_audit_events",
    "list_documents",
    "list_recent_audit_events",
    "mark_extraction_failed",
    "record_decision",
    "record_extraction_result",
]
