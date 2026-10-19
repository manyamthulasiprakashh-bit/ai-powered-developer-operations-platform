from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.routes.documents import (
    MAX_FILENAME_LENGTH,
    _sanitize_filename,
    _validate_name_and_type,
)
from app.core.config import get_settings
from app.core.exceptions import UnsupportedDocumentError
from app.db.session import get_db
from app.main import app
from app.models import Analysis, AuditEvent, Document

EXPECTED_RESPONSE_KEYS = {
    "id",
    "filename",
    "content_type",
    "size_bytes",
    "sha256",
    "status",
    "received_at",
    "updated_at",
    "text_preview",
}


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _post(client, filename, data, content_type, headers):
    return client.post(
        "/api/documents",
        files={"file": (filename, data, content_type)},
        headers=headers,
    )


def test_intake_txt_success(client, db_session, auth_headers):
    data = b"Client: Acme Corp\nTotal fee: 1000\n" + b"terms " * 200

    response = _post(client, "engagement.txt", data, "text/plain", auth_headers)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == EXPECTED_RESPONSE_KEYS
    assert body["filename"] == "engagement.txt"
    assert body["content_type"] == "text/plain"
    assert body["size_bytes"] == len(data)
    assert body["sha256"] == hashlib.sha256(data).hexdigest()
    assert body["status"] == "received"
    assert "Client: Acme Corp" in body["text_preview"]
    assert body["text_preview"] != data.decode("utf-8")
    assert "text" not in body

    stored = db_session.execute(select(Document)).scalar_one()
    assert stored.id == body["id"]
    assert stored.text == data.decode("utf-8")
    assert stored.status == "received"
    assert stored.sha256 == body["sha256"]


def test_intake_markdown_success(client, db_session, auth_headers):
    data = b"# Engagement\n\nScope summary.\n"

    response = _post(client, "notes.md", data, "text/markdown", auth_headers)

    assert response.status_code == 201
    assert response.json()["content_type"] == "text/markdown"
    assert db_session.execute(select(func.count(Document.id))).scalar_one() == 1


def test_intake_normalizes_media_type_parameters(client, auth_headers):
    response = _post(client, "a.txt", b"hello", "text/plain; charset=utf-8", auth_headers)

    assert response.status_code == 201
    assert response.json()["content_type"] == "text/plain"


def test_intake_sanitizes_filename_path(client, auth_headers):
    response = _post(client, "../../secret.txt", b"hello", "text/plain", auth_headers)

    assert response.status_code == 201
    assert response.json()["filename"] == "secret.txt"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("C:\\Users\\owner\\engagement.txt", "engagement.txt"),
        ("..\\..\\secret.txt", "secret.txt"),
        ("/tmp/../tmp/report.md", "report.md"),
        ("plain.txt", "plain.txt"),
    ],
)
def test_sanitize_filename_handles_both_path_styles(raw, expected):
    assert _sanitize_filename(raw) == expected
    assert _validate_name_and_type(
        raw,
        "text/plain",
        [".txt", ".md"],
        ["text/plain", "text/markdown"],
    )[0] == expected


@pytest.mark.parametrize(
    "raw",
    ["", ".", "..", "C:\\", "bad\x00name.txt", "bad\nname.txt"],
)
def test_sanitize_filename_rejects_empty_and_control_characters(raw):
    with pytest.raises(UnsupportedDocumentError):
        _sanitize_filename(raw)


def test_filename_length_matches_the_database_column():
    at_limit = ("a" * (MAX_FILENAME_LENGTH - len(".txt"))) + ".txt"
    over_limit = ("a" * (MAX_FILENAME_LENGTH - len(".txt") + 1)) + ".txt"

    assert len(at_limit) == MAX_FILENAME_LENGTH
    assert _sanitize_filename(at_limit) == at_limit
    with pytest.raises(UnsupportedDocumentError):
        _sanitize_filename(over_limit)


def test_intake_accepts_filename_at_the_column_limit(client, auth_headers):
    filename = ("a" * (MAX_FILENAME_LENGTH - len(".txt"))) + ".txt"

    response = _post(client, filename, b"hello", "text/plain", auth_headers)

    assert response.status_code == 201
    assert response.json()["filename"] == filename


def test_intake_rejects_overlong_filename(client, db_session, auth_headers):
    filename = ("a" * (MAX_FILENAME_LENGTH - len(".txt") + 1)) + ".txt"

    response = _post(client, filename, b"hello", "text/plain", auth_headers)

    assert response.status_code == 422
    assert response.json()["error"] == "unsupported_document"
    assert db_session.execute(select(func.count(Document.id))).scalar_one() == 0


def test_intake_requires_api_key(client, db_session):
    response = _post(client, "a.txt", b"hello", "text/plain", headers={})

    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"
    assert db_session.execute(select(func.count(Document.id))).scalar_one() == 0


def test_intake_missing_file_returns_422(client, auth_headers):
    response = client.post("/api/documents", headers=auth_headers)

    assert response.status_code == 422


def test_intake_empty_content_is_rejected(client, db_session, auth_headers):
    response = _post(client, "a.txt", b"", "text/plain", auth_headers)

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_document"
    assert db_session.execute(select(func.count(Document.id))).scalar_one() == 0


def test_intake_whitespace_only_content_is_rejected(client, auth_headers):
    response = _post(client, "a.txt", b"   \n\t  ", "text/plain", auth_headers)

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_document"


def test_intake_unsupported_extension_is_rejected(client, db_session, auth_headers):
    response = _post(client, "payload.pdf", b"%PDF-1.4", "text/plain", auth_headers)

    assert response.status_code == 422
    assert response.json()["error"] == "unsupported_document"
    assert db_session.execute(select(func.count(Document.id))).scalar_one() == 0


def test_intake_unsupported_media_type_is_rejected(client, db_session, auth_headers):
    response = _post(client, "a.txt", b"hello", "application/pdf", auth_headers)

    assert response.status_code == 422
    assert response.json()["error"] == "unsupported_document"
    assert db_session.execute(select(func.count(Document.id))).scalar_one() == 0


def test_intake_invalid_utf8_is_rejected(client, db_session, auth_headers):
    response = _post(client, "a.txt", b"\xff\xfe\x00\x01", "text/plain", auth_headers)

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_document"
    assert db_session.execute(select(func.count(Document.id))).scalar_one() == 0


def test_intake_size_limit_boundary(client, monkeypatch, auth_headers):
    monkeypatch.setenv("DOCUMENT_MAX_SIZE_BYTES", "16")
    get_settings.cache_clear()

    at_limit = _post(client, "a.txt", b"a" * 16, "text/plain", auth_headers)
    assert at_limit.status_code == 201

    over_limit = _post(client, "a.txt", b"a" * 17, "text/plain", auth_headers)
    assert over_limit.status_code == 413
    assert over_limit.json()["error"] == "document_too_large"


def test_intake_text_length_limit(client, monkeypatch, auth_headers):
    monkeypatch.setenv("DOCUMENT_MAX_TEXT_CHARS", "5")
    get_settings.cache_clear()

    assert _post(client, "a.txt", b"abcde", "text/plain", auth_headers).status_code == 201
    assert _post(client, "a.txt", b"abcdef", "text/plain", auth_headers).status_code == 413


def test_intake_preview_is_bounded_and_body_is_not_exposed(client, monkeypatch, auth_headers):
    monkeypatch.setenv("DOCUMENT_PREVIEW_CHARS", "10")
    get_settings.cache_clear()

    response = _post(client, "a.txt", b"x" * 100, "text/plain", auth_headers)

    assert response.status_code == 201
    body = response.json()
    assert body["text_preview"] == "x" * 10
    assert len(body["text_preview"]) == 10
    assert "x" * 100 not in response.text


@pytest.mark.parametrize(
    ("content", "expected_preview"),
    [
        (b"short", ""),
        (b"0123456789", ""),
        (b"0123456789X", "0123456789"),
    ],
)
def test_preview_never_returns_the_whole_short_document(
    client, monkeypatch, auth_headers, content, expected_preview
):
    monkeypatch.setenv("DOCUMENT_PREVIEW_CHARS", "10")
    get_settings.cache_clear()

    response = _post(client, "a.txt", content, "text/plain", auth_headers)

    assert response.status_code == 201
    assert response.json()["text_preview"] == expected_preview
    assert response.json()["text_preview"] != content.decode("utf-8")


def test_preview_for_long_document_is_exact_strict_prefix(client, monkeypatch, auth_headers):
    monkeypatch.setenv("DOCUMENT_PREVIEW_CHARS", "10")
    get_settings.cache_clear()
    content = b"abcdefghijklmnopqrstuvwxyz"

    response = _post(client, "a.txt", content, "text/plain", auth_headers)

    assert response.status_code == 201
    preview = response.json()["text_preview"]
    assert preview == content.decode("utf-8")[:10]
    assert len(preview) == 10
    assert preview != content.decode("utf-8")


def test_intake_persists_receipt_audit_event(client, db_session, auth_headers):
    data = b"hello world"

    response = _post(client, "a.txt", data, "text/plain", auth_headers)
    document_id = response.json()["id"]

    events = db_session.execute(select(AuditEvent)).scalars().all()
    assert len(events) == 1
    assert events[0].document_id == document_id
    assert events[0].event_type == "document_received"
    assert events[0].actor == "owner"
    assert events[0].data == {"size_bytes": len(data)}


def test_duplicate_uploads_are_allowed(client, db_session, auth_headers):
    data = b"duplicate content"

    first = _post(client, "a.txt", data, "text/plain", auth_headers)
    second = _post(client, "a.txt", data, "text/plain", auth_headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert first.json()["sha256"] == second.json()["sha256"]
    assert db_session.execute(select(func.count(Document.id))).scalar_one() == 2
    assert db_session.execute(select(func.count(AuditEvent.id))).scalar_one() == 2


def test_intake_rolls_back_and_persists_nothing_on_failure(client, db_session, monkeypatch, auth_headers):
    rollback_calls = {"count": 0}
    original_rollback = db_session.rollback

    def tracked_rollback():
        rollback_calls["count"] += 1
        return original_rollback()

    def failing_commit():
        raise RuntimeError("connection failed password=super-secret")

    monkeypatch.setattr(db_session, "commit", failing_commit)
    monkeypatch.setattr(db_session, "rollback", tracked_rollback)

    response = _post(client, "a.txt", b"hello", "text/plain", auth_headers)

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error."
    assert "super-secret" not in response.text
    assert "password" not in response.text.lower()
    assert rollback_calls["count"] == 1

    monkeypatch.undo()
    assert db_session.execute(select(func.count(Document.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(AuditEvent.id))).scalar_one() == 0


def test_existing_analysis_endpoints_remain_intact(client, db_session, auth_headers):
    response = client.get("/api/analyses", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert db_session.execute(select(func.count(Analysis.id))).scalar_one() == 0
