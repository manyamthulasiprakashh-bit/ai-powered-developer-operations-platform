from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.request_limits import DocumentBodyLimitMiddleware
from app.db.session import get_db
from app.main import app
from app.models import AuditEvent, Document


class RecordingApp:
    """Minimal inner ASGI app that records whether it was invoked and the body."""

    def __init__(self) -> None:
        self.called = False
        self.body = b""

    async def __call__(self, scope, receive, send) -> None:
        self.called = True
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                break
            self.body += message.get("body", b"")
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})


def _scope(path="/api/documents", method="POST", headers=()):
    return {"type": "http", "method": method, "path": path, "headers": list(headers)}


def _receive_from(chunks):
    queue = [
        {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
        for index, chunk in enumerate(chunks)
    ]

    async def receive():
        if queue:
            return queue.pop(0)
        return {"type": "http.disconnect"}

    return receive


def _run(middleware, scope, receive):
    sent = []

    async def send(message):
        sent.append(message)

    asyncio.run(middleware(scope, receive, send))
    return sent


@pytest.fixture()
def small_cap(monkeypatch):
    monkeypatch.setenv("DOCUMENT_MAX_SIZE_BYTES", "100")
    monkeypatch.setenv("DOCUMENT_MULTIPART_OVERHEAD_BYTES", "0")
    get_settings.cache_clear()
    yield 100


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_declared_content_length_over_cap_is_rejected_before_inner_app(small_cap):
    inner = RecordingApp()
    sent = _run(
        DocumentBodyLimitMiddleware(inner),
        _scope(headers=[(b"content-length", b"101")]),
        _receive_from([]),
    )

    assert inner.called is False
    assert sent[0]["status"] == 413
    body = json.loads(sent[1]["body"])
    assert set(body) == {"detail", "error", "message", "retryable"}
    assert body["error"] == "document_too_large"
    assert body["retryable"] is False


def test_streamed_body_over_cap_without_content_length_is_rejected(small_cap):
    inner = RecordingApp()
    sent = _run(
        DocumentBodyLimitMiddleware(inner),
        _scope(),
        _receive_from([b"a" * 60, b"b" * 60]),
    )

    assert inner.called is False
    assert sent[0]["status"] == 413
    assert json.loads(sent[1]["body"])["error"] == "document_too_large"


def test_misleading_content_length_still_rejects_oversized_stream(small_cap):
    inner = RecordingApp()
    sent = _run(
        DocumentBodyLimitMiddleware(inner),
        _scope(headers=[(b"content-length", b"10")]),
        _receive_from([b"a" * 60, b"b" * 60]),
    )

    assert inner.called is False
    assert sent[0]["status"] == 413


def test_body_within_cap_reaches_inner_app(small_cap):
    inner = RecordingApp()
    sent = _run(
        DocumentBodyLimitMiddleware(inner),
        _scope(headers=[(b"content-length", b"100")]),
        _receive_from([b"a" * 50, b"b" * 50]),
    )

    assert inner.called is True
    assert inner.body == b"a" * 50 + b"b" * 50
    assert sent[0]["status"] == 204


def test_body_without_content_length_within_cap_reaches_inner_app(small_cap):
    inner = RecordingApp()
    _run(DocumentBodyLimitMiddleware(inner), _scope(), _receive_from([b"a" * 50, b"b" * 50]))

    assert inner.called is True
    assert inner.body == b"a" * 50 + b"b" * 50


def test_other_paths_and_methods_are_passed_through(small_cap):
    inner = RecordingApp()
    _run(
        DocumentBodyLimitMiddleware(inner),
        _scope(path="/api/analyses"),
        _receive_from([b"a" * 200]),
    )
    assert inner.called is True
    assert inner.body == b"a" * 200

    other_method = RecordingApp()
    _run(
        DocumentBodyLimitMiddleware(other_method),
        _scope(method="GET"),
        _receive_from([b"a" * 200]),
    )
    assert other_method.called is True


def _forbid_multipart_parse(*args, **kwargs):
    raise AssertionError("multipart parser must not run for oversized uploads")


def test_oversized_content_length_is_413_before_parsing_and_auth(
    client, db_session, monkeypatch, small_cap
):
    import starlette.formparsers as formparsers

    monkeypatch.setattr(formparsers.MultiPartParser, "parse", _forbid_multipart_parse)

    response = client.post(
        "/api/documents",
        content=b"x" * 101,
        headers={"Content-Type": "multipart/form-data; boundary=abc"},
    )

    assert response.status_code == 413
    assert response.json()["error"] == "document_too_large"
    assert db_session.execute(select(func.count(Document.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(AuditEvent.id))).scalar_one() == 0


def test_streamed_oversized_body_is_413_before_parsing_and_auth(
    client, db_session, monkeypatch, small_cap
):
    import starlette.formparsers as formparsers

    monkeypatch.setattr(formparsers.MultiPartParser, "parse", _forbid_multipart_parse)

    def oversized_chunks():
        yield b"x" * 60
        yield b"x" * 60

    response = client.post(
        "/api/documents",
        content=oversized_chunks(),
        headers={"Content-Type": "multipart/form-data; boundary=abc"},
    )

    assert response.status_code == 413
    assert response.json()["error"] == "document_too_large"
    assert db_session.execute(select(func.count(Document.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(AuditEvent.id))).scalar_one() == 0


def test_normal_upload_within_cap_reaches_route(client, auth_headers):
    content = b"a" * 10_000

    response = client.post(
        "/api/documents",
        files={"file": ("large.txt", content, "text/plain")},
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["size_bytes"] == len(content)


def test_within_cap_still_requires_authentication(client):
    response = client.post(
        "/api/documents",
        files={"file": ("a.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"
