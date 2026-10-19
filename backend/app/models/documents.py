"""SQLAlchemy models for the V1 document-intake workflow.

Four tables form the persistence foundation for document intake, AI-assisted
extraction, human review/decision, and an append-only audit trail. They are
intentionally decoupled from the M0 API schemas: the database stores the full
document body and normalized records, while the schemas define the transport
contract (for example, a truncated ``text_preview`` instead of the stored body).

Actor identity
--------------
Single-API-key deployments have no authenticated person. ``DEFAULT_ACTOR`` is a
system-level placeholder recorded on rows that require an actor; it is not an
authenticated user identity. Real actor attribution requires the user/RBAC work
that is explicitly out of scope for V1.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

DEFAULT_ACTOR = "owner"


class DocumentStatus:
    """Canonical document lifecycle states shared by models and services."""

    RECEIVED = "received"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    EXTRACTION_FAILED = "extraction_failed"
    APPROVED = "approved"
    REJECTED = "rejected"


class AuditEventType:
    """Canonical audit event types for a document's lifecycle."""

    DOCUMENT_RECEIVED = "document_received"
    EXTRACTION_STARTED = "extraction_started"
    EXTRACTION_SUCCEEDED = "extraction_succeeded"
    EXTRACTION_FAILED = "extraction_failed"
    FIELDS_CORRECTED = "fields_corrected"
    DECISION_RECORDED = "decision_recorded"


class Document(Base):
    """A received document and its current processing status."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=DocumentStatus.RECEIVED, server_default=DocumentStatus.RECEIVED, index=True
    )
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    extractions: Mapped[list["DocumentExtraction"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentExtraction.id",
    )
    decisions: Mapped[list["DocumentDecision"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentDecision.id",
    )
    audit_events: Mapped[list["AuditEvent"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="AuditEvent.id",
    )


class DocumentExtraction(Base):
    """One extraction attempt for a document, with provider and field payloads."""

    __tablename__ = "document_extractions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    fields: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped["Document"] = relationship(back_populates="extractions")
    decisions: Mapped[list["DocumentDecision"]] = relationship(
        back_populates="extraction",
        cascade="all, delete-orphan",
        order_by="DocumentDecision.id",
    )


class DocumentDecision(Base):
    """A human approval or rejection of a document extraction."""

    __tablename__ = "document_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    extraction_id: Mapped[int] = mapped_column(
        ForeignKey("document_extractions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    corrections: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(
        String(100), nullable=False, default=DEFAULT_ACTOR, server_default=DEFAULT_ACTOR
    )
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    document: Mapped["Document"] = relationship(back_populates="decisions")
    extraction: Mapped["DocumentExtraction"] = relationship(back_populates="decisions")


class AuditEvent(Base):
    """An append-only audit event describing a document lifecycle change."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(
        String(100), nullable=False, default=DEFAULT_ACTOR, server_default=DEFAULT_ACTOR
    )
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped["Document"] = relationship(back_populates="audit_events")
