"""Pydantic contracts for the V1 document-intake workflow.

These schemas describe document metadata and processing status, AI-assisted
field extraction (value, confidence, evidence), human corrections, approval
decisions, and the append-only audit trail. They are intentionally free of
database or transport concerns so later milestones can persist and serve them.

Business fields (for example ``client_name`` or ``total_fee``) are represented
generically as extracted field names; the concrete field set is an assumption
to be validated and is not encoded here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


DocumentStatus = Literal[
    "received",
    "extracting",
    "extracted",
    "extraction_failed",
    "approved",
    "rejected",
]

ExtractionProvider = Literal["deterministic", "openai"]

ExtractionStatus = Literal["succeeded", "failed"]

DecisionKind = Literal["approve", "reject"]

DecisionOutcome = Literal["approved", "rejected"]

AuditEventType = Literal[
    "document_received",
    "extraction_started",
    "extraction_succeeded",
    "extraction_failed",
    "fields_corrected",
    "decision_recorded",
]


class FieldEvidence(BaseModel):
    """Pointer to the document text that supports an extracted value."""

    source_quote: str = Field(min_length=1, description="Exact substring supporting the value.")
    char_start: int | None = Field(default=None, ge=0, description="Start offset in the text, when known.")
    char_end: int | None = Field(default=None, ge=0, description="End offset in the text, when known.")
    page: int | None = Field(default=None, ge=1, description="Page number for paginated documents; null for text.")

    @model_validator(mode="after")
    def validate_span(self) -> "FieldEvidence":
        if self.char_start is not None and self.char_end is not None and self.char_end < self.char_start:
            raise ValueError("char_end must be greater than or equal to char_start.")
        return self


class ExtractedField(BaseModel):
    """One extracted field with a confidence score and optional evidence."""

    name: str = Field(min_length=1, description="Machine-readable field name.")
    value: str | None = Field(default=None, description="Extracted value, or null when not found.")
    confidence: float = Field(ge=0, le=1, description="Model confidence in the value, from 0 to 1.")
    evidence: FieldEvidence | None = Field(default=None, description="Supporting document text, when available.")


class ExtractionDetail(BaseModel):
    """A stored extraction attempt for one document."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="Persisted extraction identifier.")
    document_id: int = Field(description="Owning document identifier.")
    provider: ExtractionProvider = Field(description="Extractor that produced the fields.")
    model: str | None = Field(default=None, description="Provider model name, when applicable.")
    status: ExtractionStatus = Field(description="Whether the extraction succeeded.")
    fields: list[ExtractedField] = Field(default_factory=list, description="Extracted fields.")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal extraction warnings.")
    created_at: datetime = Field(description="Timestamp when the extraction was stored.")


class FieldCorrection(BaseModel):
    """A human correction applied to one extracted field."""

    name: str = Field(min_length=1, description="Field name being corrected.")
    corrected_value: str | None = Field(default=None, description="Reviewer-supplied value, or null to clear it.")
    note: str | None = Field(default=None, description="Optional reviewer note.")


class DecisionRequest(BaseModel):
    """Human approval or rejection of an extraction."""

    decision: DecisionKind = Field(description="Approve or reject the extraction.")
    corrections: list[FieldCorrection] = Field(default_factory=list, description="Field corrections to apply.")
    reason: str | None = Field(default=None, description="Required, non-empty reason when rejecting.")

    @model_validator(mode="after")
    def validate_rejection_reason(self) -> "DecisionRequest":
        if self.decision == "reject" and (self.reason is None or not self.reason.strip()):
            raise ValueError("A non-empty reason is required when rejecting a document.")
        return self


class DecisionDetail(BaseModel):
    """A persisted approval or rejection decision."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="Persisted decision identifier.")
    document_id: int = Field(description="Owning document identifier.")
    extraction_id: int = Field(description="Extraction the decision applies to.")
    decision: DecisionOutcome = Field(description="Recorded outcome.")
    corrections: list[FieldCorrection] = Field(default_factory=list, description="Corrections applied at decision time.")
    reason: str | None = Field(default=None, description="Reviewer reason, required for rejections.")
    actor: str = Field(min_length=1, description="Reviewer identity label.")
    decided_at: datetime = Field(description="Timestamp when the decision was recorded.")


class AuditEvent(BaseModel):
    """One append-only audit event in a document's lifecycle."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="Persisted audit event identifier.")
    document_id: int = Field(description="Owning document identifier.")
    event_type: AuditEventType = Field(description="Lifecycle event type.")
    actor: str = Field(min_length=1, description="Actor responsible for the event.")
    data: dict[str, Any] = Field(default_factory=dict, description="Non-sensitive event facts.")
    created_at: datetime = Field(description="Timestamp when the event was recorded.")


class DocumentSummary(BaseModel):
    """Document metadata and current processing status."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="Persisted document identifier.")
    filename: str = Field(min_length=1, description="Original filename, used for display only.")
    content_type: str = Field(min_length=1, description="Validated content type.")
    size_bytes: int = Field(ge=0, description="Size of the received document in bytes.")
    sha256: str = Field(min_length=1, description="Content hash used for integrity and deduplication.")
    status: DocumentStatus = Field(description="Current processing status.")
    received_at: datetime = Field(description="Timestamp when the document was received.")
    updated_at: datetime = Field(description="Timestamp of the last status change.")


class DocumentDetail(DocumentSummary):
    """Document metadata plus its latest extraction, decision, and audit trail."""

    text_preview: str = Field(description="Truncated text preview; never the full stored body.")
    extraction: ExtractionDetail | None = Field(default=None, description="Latest extraction, when present.")
    decision: DecisionDetail | None = Field(default=None, description="Latest decision, when present.")
    audit: list[AuditEvent] = Field(default_factory=list, description="Audit events for this document.")


class DocumentIntakeResponse(DocumentSummary):
    """Safe response for a freshly received document.

    Mirrors ``DocumentSummary`` and adds a deliberately bounded ``text_preview``.
    Longer documents yield a strict prefix capped at the configured preview
    length; documents at or below that length return an empty preview so the
    response never contains the complete stored body.
    """

    text_preview: str = Field(
        description="Strict-prefix preview, or empty when the document is not longer than the preview limit."
    )
