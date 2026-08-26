from __future__ import annotations

import asyncio
import logging
import random
import time
from enum import StrEnum
from typing import Awaitable, Callable

import httpx

from app.core.exceptions import (
    GitHubCircuitOpenError,
    GitHubHTTPError,
    GitHubRateLimitError,
    GitHubServiceError,
    GitHubTimeoutError,
)

logger = logging.getLogger(__name__)


class FailureKind(StrEnum):
    TIMEOUT = "timeout"
    CONNECTION = "connection_failure"
    RATE_LIMIT = "rate_limit"
    SERVER_ERROR = "upstream_server_error"
    CLIENT_ERROR = "upstream_client_error"
    MALFORMED_RESPONSE = "malformed_response"
    INTERNAL = "internal_error"


def classify_failure(error: BaseException) -> FailureKind:
    if isinstance(error, (GitHubTimeoutError, TimeoutError, httpx.TimeoutException)):
        return FailureKind.TIMEOUT
    if isinstance(error, (httpx.ConnectError, httpx.NetworkError, httpx.RequestError)):
        return FailureKind.CONNECTION
    if isinstance(error, GitHubRateLimitError):
        return FailureKind.RATE_LIMIT
    if isinstance(error, GitHubHTTPError):
        if error.status_code >= 500:
            return FailureKind.SERVER_ERROR
        return FailureKind.CLIENT_ERROR
    if isinstance(error, GitHubServiceError):
        if "malformed" in str(error).lower() or "invalid data" in str(error).lower():
            return FailureKind.MALFORMED_RESPONSE
        return FailureKind.INTERNAL
    return FailureKind.INTERNAL


def is_retryable(error: BaseException) -> bool:
    return classify_failure(error) in {
        FailureKind.TIMEOUT,
        FailureKind.CONNECTION,
        FailureKind.RATE_LIMIT,
        FailureKind.SERVER_ERROR,
    }


def retry_delay(attempt: int, base_delay: float, max_delay: float, jitter: float | None = None) -> float:
    exponential = min(max_delay, base_delay * (2**attempt))
    spread = exponential * 0.25 if jitter is None else jitter
    return max(0.0, min(max_delay, exponential + random.uniform(-spread, spread)))


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, enabled: bool, failure_threshold: int, reset_timeout_seconds: float, half_open_max_calls: int = 1) -> None:
        self.enabled = enabled
        self.failure_threshold = failure_threshold
        self.reset_timeout_seconds = reset_timeout_seconds
        self.half_open_max_calls = half_open_max_calls
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.opened_at: float | None = None
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

    async def before_call(self) -> None:
        if not self.enabled:
            return
        async with self._lock:
            if self.state == CircuitState.OPEN:
                if self.opened_at is None or time.monotonic() - self.opened_at < self.reset_timeout_seconds:
                    raise GitHubCircuitOpenError("GitHub circuit breaker is open.")
                self.state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                logger.warning("github_circuit event=half_open")
            if self.state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.half_open_max_calls:
                    raise GitHubCircuitOpenError("GitHub circuit breaker is open.")
                self._half_open_calls += 1

    async def record_success(self) -> None:
        if not self.enabled:
            return
        async with self._lock:
            recovered = self.state != CircuitState.CLOSED
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.opened_at = None
            self._half_open_calls = 0
            if recovered:
                logger.info("github_circuit event=recovered")

    async def record_failure(self, error: BaseException) -> None:
        if not self.enabled or not is_retryable(error):
            return
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self.opened_at = time.monotonic()
                self._half_open_calls = 0
                logger.error("github_circuit event=open reason=half_open_failure")
                return
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                self.opened_at = time.monotonic()
                logger.error("github_circuit event=open reason=failure_threshold")


async def bounded_retry(
    operation: Callable[[], Awaitable[object]],
    max_retries: int,
    base_delay: float,
    max_delay: float,
    on_retry: Callable[[int, BaseException], None] | None = None,
):
    for attempt in range(max_retries + 1):
        try:
            return await operation()
        except Exception as error:
            if not is_retryable(error) or attempt >= max_retries:
                raise
            if on_retry:
                on_retry(attempt + 1, error)
            await asyncio.sleep(retry_delay(attempt, base_delay, max_delay))