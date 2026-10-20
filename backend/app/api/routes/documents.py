from __future__ import annotations

import hashlib
import logging
import re
from pathlib import PurePosixPath
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Path as ApiPath,
    Query,
    UploadFile,
    status,
)
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import (
    DocumentNotFoundError,
    DocumentNotDecidableError,
    DocumentNotExtractableError,
    DocumentTooLargeError,
    InvalidDocumentError,
    UnsupportedDocumentError,
)
from app.core.security import require_api_key
from app.db.session import get_db
from app.models.documents import DocumentStatus
from app.schemas.documents import (
    AuditEvent,
    AuditEventListResponse,
    DecisionDetail,
    DecisionRequest,
    DocumentDetail,
    DocumentIntakeResponse,
    DocumentListResponse,
    DocumentSummary,
    ExtractionDetail,
)
from app.services.document_extraction import run_deterministic_extraction
from app.services.document_persistence import (
    create_document,
    get_document,
    get_latest_decision,
    get_latest_extraction,
    list_audit_events,
    list_documents,
    list_recent_audit_events,
    record_decision,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Documents"], dependencies=[Depends(require_api_key)])

READ_CHUNK_SIZE = 64 * 1024
SAFE_DB_ERROR_DETAIL = "Internal server error."
# Matches the ``Document.filename`` column width so PostgreSQL never raises a
# data-truncation error that the route would have to translate at write time.
MAX_FILENAME_LENGTH = 255
# Reject control characters (including NUL) that cannot be stored or rendered
# safely and can corrupt multipart/log handling.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def _sanitize_filename(filename: str) -> str:
    """Return a safe basename from an untrusted client-supplied filename.

    Both POSIX ``/`` and Windows ``\\`` separators are treated as path
    separators regardless of the host OS, so a Windows-style path cannot smuggle
    directory components into PostgreSQL on Linux. The result is a single path
    component with no control characters and a bounded length.
    """
    basename = filename.replace("\\", "/").rsplit("/", 1)[-1]
    if not basename or basename in {".", ".."}:
        raise UnsupportedDocumentError()
    if _CONTROL_CHARS.search(basename):
        raise UnsupportedDocumentError()
    if len(basename) > MAX_FILENAME_LENGTH:
        raise UnsupportedDocumentError()
    return basename


def _validate_name_and_type(
    filename: str,
    content_type: str | None,
    allowed_extensions: list[str],
    allowed_content_types: list[str],
) -> tuple[str, str]:
    """Validate the untrusted filename extension and declared media type.

    Neither value is trusted on its own: the caller still decodes the bytes as
    strict UTF-8 afterwards. Returns the sanitized basename and normalized type.
    """
    safe_name = _sanitize_filename(filename)

    extension = PurePosixPath(safe_name).suffix.lower()
    if extension not in allowed_extensions:
        raise UnsupportedDocumentError()

    normalized_type = (content_type or "").split(";")[0].strip().lower()
    if normalized_type not in allowed_content_types:
        raise UnsupportedDocumentError()

    return safe_name, normalized_type


async def _read_bounded(file: UploadFile, max_bytes: int) -> bytes:
    """Read the upload in bounded chunks and enforce the exact file-size limit.

    The whole-request cap is enforced upstream by ``DocumentBodyLimitMiddleware``
    before multipart parsing; this check bounds the retained file payload itself.
    """
    data = bytearray()
    while True:
        chunk = await file.read(READ_CHUNK_SIZE)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > max_bytes:
            raise DocumentTooLargeError()
    return bytes(data)


def _bounded_preview(text: str, limit: int) -> str:
    """Return a strict prefix for documents longer than ``limit``.

    Documents at or below the preview limit return an empty preview so the
    response can never contain the complete stored body.
    """
    if len(text) <= limit:
        return ""
    return text[:limit]


def _store_document(
    db: Session,
    *,
    filename: str,
    content_type: str,
    size_bytes: int,
    sha256: str,
    text: str,
    preview_chars: int,
) -> DocumentIntakeResponse:
    """Persist the document and its receipt event, then build the safe response."""
    document = create_document(
        db,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        sha256=sha256,
        text=text,
        status=DocumentStatus.RECEIVED,
    )
    return DocumentIntakeResponse(
        id=document.id,
        filename=document.filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        sha256=document.sha256,
        status=document.status,
        received_at=document.received_at,
        updated_at=document.updated_at,
        text_preview=_bounded_preview(text, preview_chars),
    )


def _extract_document(db: Session, document_id: int) -> ExtractionDetail:
    """Extract synchronously and convert the stored row to the API contract."""
    record = run_deterministic_extraction(db, document_id)
    return ExtractionDetail.model_validate(record)


def _load_document_detail(
    db: Session, document_id: int, preview_chars: int
) -> DocumentDetail:
    """Build the read-only document detail contract from persisted records.

    Only a bounded preview of the stored body is returned; the latest extraction,
    latest decision, and a bounded recent slice of audit events are attached.
    """
    document = get_document(db, document_id)
    if document is None:
        raise DocumentNotFoundError()

    extraction = get_latest_extraction(db, document_id)
    decision = get_latest_decision(db, document_id)
    audit_events = list_recent_audit_events(db, document_id)
    summary = DocumentSummary.model_validate(document)

    return DocumentDetail(
        **summary.model_dump(),
        text_preview=_bounded_preview(document.text or "", preview_chars),
        extraction=ExtractionDetail.model_validate(extraction) if extraction else None,
        decision=DecisionDetail.model_validate(decision) if decision else None,
        audit=[AuditEvent.model_validate(event) for event in audit_events],
    )


def _record_document_decision(
    db: Session, document_id: int, payload: DecisionRequest
) -> DecisionDetail:
    """Record a review decision and convert the stored row to the API contract."""
    record = record_decision(
        db,
        document_id=document_id,
        decision=payload.decision,
        corrections=[correction.model_dump() for correction in payload.corrections],
        reason=payload.reason,
    )
    return DecisionDetail.model_validate(record)


@router.post(
    "/documents",
    response_model=DocumentIntakeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Receive a document",
    description=(
        "Validate and persist one .txt or .md document for the intake workflow. "
        "The document body is stored but never returned; only a bounded preview is included."
    ),
)
async def receive_document(
    file: Annotated[UploadFile, File(description="A .txt or .md document encoded as UTF-8.")],
    db: Annotated[Session, Depends(get_db)],
):
    settings = get_settings()

    filename, content_type = _validate_name_and_type(
        file.filename or "",
        file.content_type,
        settings.document_allowed_extensions,
        settings.document_allowed_content_types,
    )

    data = await _read_bounded(file, settings.document_max_size_bytes)
    if not data:
        raise InvalidDocumentError()

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidDocumentError() from exc

    if not text.strip():
        raise InvalidDocumentError()
    if len(text) > settings.document_max_text_chars:
        raise DocumentTooLargeError()

    sha256 = hashlib.sha256(data).hexdigest()

    try:
        return await run_in_threadpool(
            _store_document,
            db,
            filename=filename,
            content_type=content_type,
            size_bytes=len(data),
            sha256=sha256,
            text=text,
            preview_chars=settings.document_preview_chars,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("document_intake_persistence_failed error=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=SAFE_DB_ERROR_DETAIL,
        ) from exc


@router.post(
    "/documents/{document_id}/extractions",
    response_model=ExtractionDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Extract document fields deterministically",
    description=(
        "Run the deterministic, local extractor against an already-stored document. "
        "Recognized label lines are echoed verbatim; missing or ambiguous fields are "
        "returned with null values. Document content is never executed as instructions. "
        "Each call records a new extraction attempt; an attempt that cannot read the "
        "stored text is returned with status 'failed'."
    ),
    responses={
        404: {"description": "Document not found."},
        409: {"description": "Document is not in an extractable state."},
    },
)
async def extract_document_fields(
    document_id: Annotated[int, ApiPath(ge=1, description="Stored document identifier.")],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        return await run_in_threadpool(_extract_document, db, document_id)
    except (DocumentNotFoundError, DocumentNotExtractableError):
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("document_extraction_failed error=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=SAFE_DB_ERROR_DETAIL,
        ) from exc


@router.post(
    "/documents/{document_id}/decisions",
    response_model=DecisionDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Record a document decision",
    description=(
        "Approve or reject the latest successful extraction while the document is "
        "in the extracted state. Corrections are stored on the decision and audit "
        "trail without mutating the original extraction. A document may be decided "
        "once; later decisions return 409."
    ),
    responses={
        404: {"description": "Document not found."},
        409: {"description": "Document is not in a decidable state."},
    },
)
async def decide_document(
    document_id: Annotated[int, ApiPath(ge=1, description="Stored document identifier.")],
    payload: DecisionRequest,
    db: Annotated[Session, Depends(get_db)],
):
    try:
        return await run_in_threadpool(
            _record_document_decision, db, document_id, payload
        )
    except (DocumentNotFoundError, DocumentNotDecidableError):
        raise
    except SQLAlchemyError as exc:
        logger.error("document_decision_failed error=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=SAFE_DB_ERROR_DETAIL,
        ) from exc


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    summary="List stored documents",
    description="Return stored documents newest first with bounded pagination.",
)
async def list_document_records(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    try:
        records, total = await run_in_threadpool(list_documents, db, limit, offset)
    except SQLAlchemyError as exc:
        logger.error("document_list_failed error=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=SAFE_DB_ERROR_DETAIL,
        ) from exc

    return DocumentListResponse(
        items=[DocumentSummary.model_validate(record) for record in records],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/documents/{document_id}",
    response_model=DocumentDetail,
    summary="Get a stored document",
    description=(
        "Return document metadata, a bounded text preview, the latest extraction, "
        "the latest decision, and a bounded recent audit slice. The complete stored "
        "text is never returned."
    ),
    responses={404: {"description": "Document not found."}},
)
async def get_document_detail(
    document_id: Annotated[int, ApiPath(ge=1, description="Stored document identifier.")],
    db: Annotated[Session, Depends(get_db)],
):
    settings = get_settings()
    try:
        return await run_in_threadpool(
            _load_document_detail, db, document_id, settings.document_preview_chars
        )
    except DocumentNotFoundError:
        raise
    except SQLAlchemyError as exc:
        logger.error("document_detail_failed error=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=SAFE_DB_ERROR_DETAIL,
        ) from exc


@router.get(
    "/documents/{document_id}/audit",
    response_model=AuditEventListResponse,
    summary="List a document's audit trail",
    description=(
        "Return one chronological page of a document's append-only audit events. "
        "Event payloads contain non-sensitive lifecycle facts only."
    ),
    responses={404: {"description": "Document not found."}},
)
async def list_document_audit_events(
    document_id: Annotated[int, ApiPath(ge=1, description="Stored document identifier.")],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    try:
        document = await run_in_threadpool(get_document, db, document_id)
        if document is None:
            raise DocumentNotFoundError()
        records, total = await run_in_threadpool(
            list_audit_events, db, document_id, limit, offset
        )
    except DocumentNotFoundError:
        raise
    except SQLAlchemyError as exc:
        logger.error("document_audit_list_failed error=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=SAFE_DB_ERROR_DETAIL,
        ) from exc

    return AuditEventListResponse(
        items=[AuditEvent.model_validate(record) for record in records],
        total=total,
        limit=limit,
        offset=offset,
    )
