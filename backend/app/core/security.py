from __future__ import annotations

import hmac
import re
import time
from collections import defaultdict, deque
from collections.abc import Iterable
from threading import Lock
from typing import Annotated
from urllib.parse import urlparse

from fastapi import Header

from app.core.exceptions import AuthenticationConfigurationError, AuthenticationError


API_KEY_HEADER = "X-API-Key"

SENSITIVE_VALUE_PATTERN = re.compile(
    r"(?i)(authorization|cookie|token|password|api[_-]?key|secret)(\s*[:=]\s*)([^\s,;]+)"
)


def redact_sensitive(value: object) -> str:
    return SENSITIVE_VALUE_PATTERN.sub(r"\1\2[REDACTED]", str(value))


def require_api_key(
    provided: Annotated[str | None, Header(alias=API_KEY_HEADER)] = None,
) -> None:
    """Enforce API-key authentication for protected endpoints.

    Fails closed: when no server-side key is configured the request is denied
    rather than allowed. The supplied value is never logged or returned.
    """
    from app.core.config import get_settings

    configured = get_settings().api_key
    if not configured or not configured.strip():
        raise AuthenticationConfigurationError()
    candidate = provided or ""
    if not hmac.compare_digest(candidate.encode("utf-8"), configured.encode("utf-8")):
        raise AuthenticationError()


def validate_cors_origins(origins: list[str], environment: str) -> list[str]:
    normalized = [origin.strip().rstrip("/") for origin in origins if origin.strip()]
    if environment == "production" and not normalized:
        raise ValueError("CORS_ALLOWED_ORIGINS must be configured in production.")

    for origin in normalized:
        parsed = urlparse(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"}:
            raise ValueError("CORS origins must be absolute HTTP(S) origins.")
        if origin == "*":
            raise ValueError("Wildcard CORS origins are not allowed.")
        if environment == "production" and parsed.scheme != "https":
            raise ValueError("Production CORS origins must use HTTPS.")
    return normalized


class InMemoryRateLimiter:
    """Process-local limiter with a replaceable interface for a distributed store later."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        if max_requests < 1 or window_seconds < 1:
            raise ValueError("Rate limit values must be positive.")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str, now: float | None = None) -> tuple[bool, int]:
        current_time = time.monotonic() if now is None else now
        with self._lock:
            requests = self._requests[key]
            cutoff = current_time - self.window_seconds
            while requests and requests[0] <= cutoff:
                requests.popleft()
            if len(requests) >= self.max_requests:
                retry_after = max(1, int(requests[0] + self.window_seconds - current_time))
                return False, retry_after
            requests.append(current_time)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()


ROUTE_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("POST", re.compile(r"^/api/github/repositories/[^/]+/[^/]+/analysis$"), "/api/github/repositories/{owner}/{repo}/analysis"),
    ("GET", re.compile(r"^/api/github/repositories/[^/]+/[^/]+/commits$"), "/api/github/repositories/{owner}/{repo}/commits"),
    ("GET", re.compile(r"^/api/github/repositories/[^/]+/[^/]+/pull-requests$"), "/api/github/repositories/{owner}/{repo}/pull-requests"),
    ("GET", re.compile(r"^/api/github/repositories/[^/]+/[^/]+/issues$"), "/api/github/repositories/{owner}/{repo}/issues"),
    ("GET", re.compile(r"^/api/github/repositories/[^/]+/[^/]+/contents$"), "/api/github/repositories/{owner}/{repo}/contents"),
    ("GET", re.compile(r"^/api/github/repositories/[^/]+/[^/]+$"), "/api/github/repositories/{owner}/{repo}"),
    ("GET", re.compile(r"^/api/analyses/[^/]+$"), "/api/analyses/{analysis_id}"),
    ("GET", re.compile(r"^/api/analyses$"), "/api/analyses"),
    ("GET", re.compile(r"^/api/statistics$"), "/api/statistics"),
    ("GET", re.compile(r"^/api/documents$"), "/api/documents"),
    ("GET", re.compile(r"^/api/documents/[^/]+/audit$"), "/api/documents/{document_id}/audit"),
    ("GET", re.compile(r"^/api/documents/[^/]+$"), "/api/documents/{document_id}"),
    ("POST", re.compile(r"^/api/documents$"), "/api/documents"),
    ("POST", re.compile(r"^/api/documents/[^/]+/decisions$"), "/api/documents/{document_id}/decisions"),
)


def categorize_request(method: str, path: str) -> str:
    """Map a concrete request to a stable route template.

    Middleware runs before route matching, so path parameters such as owner and
    repository must be collapsed here to prevent per-repository rate-limit
    buckets. Unknown paths share a single category.
    """
    for expected_method, pattern, template in ROUTE_PATTERNS:
        if expected_method == method and pattern.match(path):
            return template
    return "other"


def resolve_client_identity(
    peer_host: str | None,
    forwarded_for: str | None,
    trusted_proxies: Iterable[str],
) -> str:
    """Resolve a stable client identity without blindly trusting headers.

    ``X-Forwarded-For`` is honored only when the direct peer is an explicitly
    trusted proxy; otherwise the peer address is used as-is.
    """
    peer = peer_host or "unknown"
    if forwarded_for and peer in set(trusted_proxies):
        first = forwarded_for.split(",")[0].strip()
        if first:
            return first
    return peer
