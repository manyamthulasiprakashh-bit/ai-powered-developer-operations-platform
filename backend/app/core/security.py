from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from threading import Lock
from urllib.parse import urlparse


SENSITIVE_VALUE_PATTERN = re.compile(
    r"(?i)(authorization|cookie|token|password|api[_-]?key|secret)(\s*[:=]\s*)([^\s,;]+)"
)


def redact_sensitive(value: object) -> str:
    return SENSITIVE_VALUE_PATTERN.sub(r"\1\2[REDACTED]", str(value))


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