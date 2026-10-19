"""Pre-routing request-body limits for the document intake endpoint.

FastAPI parses multipart bodies and resolves authentication dependencies inside
the route handler, and Starlette's multipart parser does not cap file-part size.
This pure-ASGI middleware therefore runs inside the routing stack (before FastAPI
parses the body and before ``require_api_key`` executes) and enforces a hard cap
on the entire upload request.

It follows a bounded pre-read-and-replay strategy: at most
``document_max_request_bytes`` of body is buffered before the inner app runs. If
the declared ``Content-Length`` or the streamed bytes exceed the cap, a safe 413
response is sent and the inner app is never invoked. Buffered body size is
therefore bounded by the configured cap, and multipart parsing never sees an
oversized request.
"""

from __future__ import annotations

import json
import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)

DOCUMENT_UPLOAD_PATH = "/api/documents"
DOCUMENT_UPLOAD_PATHS = frozenset({DOCUMENT_UPLOAD_PATH, f"{DOCUMENT_UPLOAD_PATH}/"})

TOO_LARGE_BODY = {
    "detail": "Document exceeds the maximum allowed size.",
    "error": "document_too_large",
    "message": "Document exceeds the maximum allowed size.",
    "retryable": False,
}


def _declared_content_length(scope: dict) -> int | None:
    """Return the largest declared Content-Length, ignoring malformed values."""
    lengths: list[int] = []
    for name, value in scope.get("headers", []):
        if name.lower() != b"content-length":
            continue
        try:
            lengths.append(int(value))
        except (TypeError, ValueError):
            continue
    return max(lengths) if lengths else None


async def _send_too_large(send) -> None:
    payload = json.dumps(TOO_LARGE_BODY).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode("ascii")),
                (b"x-content-type-options", b"nosniff"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload, "more_body": False})


class DocumentBodyLimitMiddleware:
    """Bound the request body for ``POST /api/documents`` before it is parsed."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if (
            scope.get("type") != "http"
            or scope.get("method") != "POST"
            or scope.get("path") not in DOCUMENT_UPLOAD_PATHS
        ):
            await self.app(scope, receive, send)
            return

        cap = get_settings().document_max_request_bytes

        declared = _declared_content_length(scope)
        if declared is not None and declared > cap:
            logger.warning("document_request_body_too_large declared_bytes=%s cap=%s", declared, cap)
            await _send_too_large(send)
            return

        # Bounded pre-read: buffer only messages whose body still fits under the
        # cap, then replay them to the inner app. Exactly one message may carry
        # the final body chunk, and its size is checked before buffering.
        messages: list[dict] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                messages.append(message)
                break
            if message["type"] != "http.request":
                messages.append(message)
                continue
            body = message.get("body", b"")
            if total + len(body) > cap:
                logger.warning("document_request_body_too_large streamed_cap=%s", cap)
                await _send_too_large(send)
                return
            messages.append(message)
            total += len(body)
            if not message.get("more_body", False):
                break

        index = 0

        async def replay():
            nonlocal index
            if index < len(messages):
                buffered = messages[index]
                index += 1
                return buffered
            return await receive()

        await self.app(scope, replay, send)
