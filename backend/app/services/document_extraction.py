"""Deterministic, local field extraction for received plain-text documents.

This service intentionally does not call a model, network service, or external
provider. It recognizes a deliberately small set of label lines and returns the
text following each label as-is:

===============  ==========================================
Field            Accepted labels (case-insensitive)
===============  ==========================================
``client_name``  ``Client``, ``Client Name``
``total_fee``    ``Total Fee``, ``Fee``
``effective_date``  ``Effective Date``
``reference_id``  ``Reference``, ``Reference ID``, ``Ref``, ``Ref ID``
===============  ==========================================

Rules and limits
----------------
- A label must begin a line (leading whitespace is allowed) and be followed by
  an ASCII colon. Labels may use spaces, underscores, or hyphens
  interchangeably (``Client_Name`` matches ``Client Name``). Markdown
  decoration, full-width punctuation, and inline labels are not supported.
- The value is the trimmed text after the colon, preserved verbatim. No
  numeric, currency, or date normalization is attempted.
- Repeated identical values are accepted using the first occurrence. Two or
  more distinct values for one field are ambiguous: the field is returned with
  ``value=None`` and an ``ambiguous:<field>`` warning instead of guessing.
- Missing fields are represented as ``value=None``, ``confidence=0.0``, and no
  evidence. An empty label value is ignored with an ``empty_value:<field>``
  warning.
- Evidence is the complete trimmed label line. ``char_start``/``char_end`` are
  Unicode code-point offsets into ``Document.text`` and ``char_end`` is
  exclusive; the span is validated against the stored text before emission.
- Confidence is ``0.95`` for an unambiguous label match and ``0.0`` when the
  field is missing or ambiguous. ``no_fields_found`` is added when no field
  resolves to a value.
- Document content is always treated as data. Instructions in the document are
  never executed, interpreted as commands, or allowed to change status.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import DocumentNotFoundError, DocumentNotExtractableError
from app.models.documents import (
    AuditEventType,
    Document,
    DocumentExtraction,
    DocumentStatus,
)
from app.schemas.documents import ExtractedField, FieldEvidence
from app.services.document_persistence import (
    EXTRACTABLE_STATUSES,
    claim_document_for_extraction,
    get_document,
    mark_extraction_failed,
    record_extraction_result,
)

PROVIDER = "deterministic"
MODEL: str | None = None

FIELD_ORDER: tuple[str, ...] = ("client_name", "total_fee", "effective_date", "reference_id")

FIELD_LABELS: dict[str, frozenset[str]] = {
    "client_name": frozenset({"client", "client name"}),
    "total_fee": frozenset({"total fee", "fee"}),
    "effective_date": frozenset({"effective date"}),
    "reference_id": frozenset({"reference", "reference id", "ref", "ref id"}),
}

CONFIDENCE_FOUND = 0.95
CONFIDENCE_MISSING = 0.0

_LABEL_LINE = re.compile(r"^(?P<label>[A-Za-z][A-Za-z0-9 _-]{0,63}?)\s*:\s*(?P<value>.*)$")
_LABEL_TO_FIELD = {
    label: field_name
    for field_name, labels in FIELD_LABELS.items()
    for label in labels
}


@dataclass(frozen=True)
class ExtractionResult:
    """Deterministic extraction outcome prior to persistence."""

    status: str
    fields: list[dict[str, Any]]
    warnings: list[str]


def _normalize_label(label: str) -> str:
    return " ".join(label.replace("_", " ").replace("-", " ").lower().split())


def _iter_trimmed_lines(text: str):
    """Yield ``(quote, start, end)`` for each non-blank line of ``text``.

    Offsets are code-point indexes into ``text`` and ``end`` is exclusive, so
    ``text[start:end] == quote`` always holds for the yielded values.
    """
    offset = 0
    for raw_line in text.splitlines(keepends=True):
        quote = raw_line.strip()
        if quote:
            leading = len(raw_line) - len(raw_line.lstrip())
            start = offset + leading
            yield quote, start, start + len(quote)
        offset += len(raw_line)


def _build_evidence(text: str, quote: str, start: int, end: int) -> FieldEvidence:
    if end <= start or text[start:end] != quote:
        raise ValueError("Evidence offsets do not match the stored document text.")
    return FieldEvidence(source_quote=quote, char_start=start, char_end=end, page=None)


def extract_fields(text: str | None) -> ExtractionResult:
    """Extract the documented fields from ``text`` without side effects."""
    if text is None or not text.strip():
        return ExtractionResult(
            status="failed",
            fields=[],
            warnings=["document_text_unavailable"],
        )

    occurrences: dict[str, list[tuple[str, int, int, str]]] = {
        field_name: [] for field_name in FIELD_ORDER
    }
    warnings: list[str] = []

    for quote, start, end in _iter_trimmed_lines(text):
        match = _LABEL_LINE.match(quote)
        if match is None:
            continue
        field_name = _LABEL_TO_FIELD.get(_normalize_label(match.group("label")))
        if field_name is None:
            continue
        value = match.group("value").strip()
        if not value:
            warnings.append(f"empty_value:{field_name}")
            continue
        occurrences[field_name].append((value, start, end, quote))

    fields: list[ExtractedField] = []
    for field_name in FIELD_ORDER:
        found = occurrences[field_name]
        if not found:
            fields.append(
                ExtractedField(
                    name=field_name,
                    value=None,
                    confidence=CONFIDENCE_MISSING,
                    evidence=None,
                )
            )
            continue

        distinct_values = {value for value, _start, _end, _quote in found}
        if len(distinct_values) > 1:
            warnings.append(f"ambiguous:{field_name}")
            fields.append(
                ExtractedField(
                    name=field_name,
                    value=None,
                    confidence=CONFIDENCE_MISSING,
                    evidence=None,
                )
            )
            continue

        value, start, end, quote = found[0]
        fields.append(
            ExtractedField(
                name=field_name,
                value=value,
                confidence=CONFIDENCE_FOUND,
                evidence=_build_evidence(text, quote, start, end),
            )
        )

    if all(extracted.value is None for extracted in fields):
        warnings.append("no_fields_found")

    return ExtractionResult(
        status="succeeded",
        fields=[extracted.model_dump() for extracted in fields],
        warnings=list(dict.fromkeys(warnings)),
    )


def run_deterministic_extraction(db: Session, document_id: int) -> DocumentExtraction:
    """Claim the document, extract, then persist the final attempt atomically.

    The claim is a conditional update that writes ``extraction_started`` in the
    same transaction, so two concurrent callers cannot both move the same
    document into ``extracting``. Finalization writes the attempt, final status,
    and success/failure event together. If extraction raises unexpectedly, the
    document is moved to ``extraction_failed`` instead of remaining stuck in
    ``extracting``; the original exception still propagates.
    """
    document = claim_document_for_extraction(
        db, document_id=document_id, provider=PROVIDER
    )
    if document is None:
        if get_document(db, document_id) is None:
            raise DocumentNotFoundError()
        raise DocumentNotExtractableError()

    try:
        result = extract_fields(document.text)
        succeeded = result.status == "succeeded"
        document_status = (
            DocumentStatus.EXTRACTED if succeeded else DocumentStatus.EXTRACTION_FAILED
        )
        final_event = (
            AuditEventType.EXTRACTION_SUCCEEDED if succeeded else AuditEventType.EXTRACTION_FAILED
        )
        missing_count = sum(1 for field in result.fields if field["value"] is None)

        return record_extraction_result(
            db,
            document=document,
            provider=PROVIDER,
            model=MODEL,
            fields=result.fields,
            status=result.status,
            document_status=document_status,
            warnings=result.warnings,
            audit_events=[
                {
                    "event_type": final_event,
                    "data": {
                        "provider": PROVIDER,
                        "status": result.status,
                        "field_count": len(result.fields),
                        "missing_count": missing_count,
                    },
                },
            ],
        )
    except Exception:
        mark_extraction_failed(db, document)
        raise


__all__ = [
    "CONFIDENCE_FOUND",
    "CONFIDENCE_MISSING",
    "EXTRACTABLE_STATUSES",
    "FIELD_LABELS",
    "FIELD_ORDER",
    "MODEL",
    "PROVIDER",
    "ExtractionResult",
    "extract_fields",
    "run_deterministic_extraction",
]
