from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from app.core.exceptions import (
    DocumentTooLargeError,
    ExtractionOutputError,
    ExtractionProviderError,
    ExtractionTimeoutError,
    UnsupportedDocumentError,
)
from app.schemas.documents import (
    AuditEvent,
    DecisionDetail,
    DecisionRequest,
    DocumentDetail,
    DocumentSummary,
    ExtractedField,
    ExtractionDetail,
    FieldCorrection,
    FieldEvidence,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _request() -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/documents",
        "headers": [],
        "query_string": b"",
        "scheme": "http",
        "server": ("testserver", 80),
        "root_path": "",
    }
    return Request(scope)


def _extraction() -> ExtractionDetail:
    return ExtractionDetail(
        id=1,
        document_id=1,
        provider="deterministic",
        model=None,
        status="succeeded",
        fields=[
            ExtractedField(
                name="client_name",
                value="Acme Corp",
                confidence=0.8,
                evidence=FieldEvidence(source_quote="Client: Acme Corp", char_start=0, char_end=18),
            )
        ],
        warnings=["provider_failed_fallback"],
        created_at=NOW,
    )


def _decision() -> DecisionDetail:
    return DecisionDetail(
        id=1,
        document_id=1,
        extraction_id=1,
        decision="approved",
        corrections=[FieldCorrection(name="client_name", corrected_value="Acme Corporation", note="Legal name")],
        reason=None,
        actor="owner",
        decided_at=NOW,
    )


def test_valid_document_summary_payload():
    summary = DocumentSummary(
        id=1,
        filename="engagement.txt",
        content_type="text/plain",
        size_bytes=2048,
        sha256="a" * 64,
        status="extracted",
        received_at=NOW,
        updated_at=NOW,
    )
    assert summary.status == "extracted"
    assert summary.size_bytes == 2048


def test_valid_document_detail_payload_round_trips_nested_models():
    detail = DocumentDetail(
        id=1,
        filename="engagement.txt",
        content_type="text/plain",
        size_bytes=2048,
        sha256="a" * 64,
        status="approved",
        received_at=NOW,
        updated_at=NOW,
        text_preview="Client: Acme Corp",
        extraction=_extraction(),
        decision=_decision(),
        audit=[
            AuditEvent(
                id=1,
                document_id=1,
                event_type="document_received",
                actor="owner",
                data={"size_bytes": 2048},
                created_at=NOW,
            )
        ],
    )
    assert detail.extraction.fields[0].evidence.source_quote == "Client: Acme Corp"
    assert detail.decision.corrections[0].corrected_value == "Acme Corporation"
    assert detail.audit[0].event_type == "document_received"


@pytest.mark.parametrize("status", ["unknown", "pending", "done", ""])
def test_document_status_rejects_invalid_literals(status):
    with pytest.raises(ValidationError):
        DocumentSummary(
            id=1,
            filename="engagement.txt",
            content_type="text/plain",
            size_bytes=1,
            sha256="a",
            status=status,
            received_at=NOW,
            updated_at=NOW,
        )


def test_extraction_rejects_invalid_status_and_provider():
    with pytest.raises(ValidationError):
        ExtractionDetail(id=1, document_id=1, provider="deterministic", status="pending", created_at=NOW)
    with pytest.raises(ValidationError):
        ExtractionDetail(id=1, document_id=1, provider="other", status="succeeded", created_at=NOW)


def test_decision_detail_rejects_invalid_outcome():
    with pytest.raises(ValidationError):
        DecisionDetail(
            id=1,
            document_id=1,
            extraction_id=1,
            decision="maybe",
            actor="owner",
            decided_at=NOW,
        )


def test_audit_event_rejects_invalid_event_type():
    with pytest.raises(ValidationError):
        AuditEvent(id=1, document_id=1, event_type="something_else", actor="owner", created_at=NOW)


@pytest.mark.parametrize("confidence", [-0.01, 1.01, -1, 2])
def test_extracted_field_confidence_outside_unit_interval(confidence):
    with pytest.raises(ValidationError):
        ExtractedField(name="client_name", value="Acme", confidence=confidence)


@pytest.mark.parametrize("confidence", [0, 0.5, 1])
def test_extracted_field_confidence_bounds_are_inclusive(confidence):
    field = ExtractedField(name="client_name", value="Acme", confidence=confidence)
    assert field.confidence == confidence


def test_field_evidence_rejects_reversed_span():
    with pytest.raises(ValidationError):
        FieldEvidence(source_quote="Acme", char_start=10, char_end=4)


@pytest.mark.parametrize("reason", [None, "", "   ", "\t\n"])
def test_rejection_requires_non_blank_reason(reason):
    with pytest.raises(ValidationError):
        DecisionRequest(decision="reject", reason=reason)


def test_rejection_with_reason_is_valid():
    request = DecisionRequest(decision="reject", reason="Missing signature page.")
    assert request.reason == "Missing signature page."


def test_approval_does_not_require_a_reason():
    request = DecisionRequest(decision="approve", corrections=[FieldCorrection(name="end_date", corrected_value="2026-06-30")])
    assert request.reason is None
    assert request.corrections[0].name == "end_date"


def test_list_and_dict_defaults_are_isolated_between_instances():
    first = DecisionRequest(decision="approve")
    second = DecisionRequest(decision="approve")
    first.corrections.append(FieldCorrection(name="total_fee", corrected_value="1000"))
    assert second.corrections == []
    assert first.corrections is not second.corrections

    first_event = AuditEvent(id=1, document_id=1, event_type="document_received", actor="owner", created_at=NOW)
    second_event = AuditEvent(id=2, document_id=1, event_type="document_received", actor="owner", created_at=NOW)
    first_event.data["extra"] = True
    assert second_event.data == {}
    assert first_event.data is not second_event.data

    assert ExtractionDetail(id=1, document_id=1, provider="deterministic", status="succeeded", created_at=NOW).fields == []


@pytest.mark.parametrize(
    ("handler_name", "error", "expected_status", "expected_error", "expected_retryable"),
    [
        ("unsupported_document_exception_handler", UnsupportedDocumentError(), 422, "unsupported_document", False),
        ("document_too_large_exception_handler", DocumentTooLargeError(), 413, "document_too_large", False),
        ("extraction_timeout_exception_handler", ExtractionTimeoutError(), 504, "extraction_timeout", True),
        ("extraction_output_exception_handler", ExtractionOutputError(), 502, "extraction_output_invalid", True),
        ("extraction_provider_exception_handler", ExtractionProviderError(), 502, "extraction_provider_unavailable", True),
    ],
)
def test_document_exception_handlers_return_safe_contracts(
    handler_name, error, expected_status, expected_error, expected_retryable
):
    import app.main as main_module

    handler = getattr(main_module, handler_name)
    response = asyncio.run(handler(_request(), error))
    body = json.loads(response.body)

    assert response.status_code == expected_status
    assert body["error"] == expected_error
    assert body["retryable"] is expected_retryable
    assert set(body) == {"detail", "error", "message", "retryable"}
    assert body["detail"] == body["message"]
    assert body["detail"].strip() != ""
    assert "Traceback" not in body["detail"]


def test_extraction_output_error_is_a_provider_error_subtype():
    assert issubclass(ExtractionOutputError, ExtractionProviderError)
    assert issubclass(ExtractionTimeoutError, ExtractionProviderError)
