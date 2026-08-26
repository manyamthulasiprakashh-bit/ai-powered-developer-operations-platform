from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.exceptions import (
    GitHubAuthError,
    GitHubHTTPError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubServiceError,
    GitHubTimeoutError,
)
from app.core.reliability import CircuitBreaker, bounded_retry, is_retryable

logger = logging.getLogger(__name__)


class GitHubClient:
    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.github_api_url or "https://api.github.com").rstrip("/")
        self.token = token or settings.github_token
        self.timeout = httpx.Timeout(settings.github_read_timeout, connect=settings.github_connect_timeout)
        self.limits = httpx.Limits(
            max_connections=settings.github_max_connections,
            max_keepalive_connections=settings.github_max_keepalive_connections,
        )
        self._async_client: httpx.AsyncClient | None = None
        self.max_retries = settings.github_max_retries
        self.retry_base_delay = settings.github_retry_base_delay_seconds
        self.retry_max_delay = settings.github_retry_max_delay_seconds
        self.circuit_breaker = CircuitBreaker(
            enabled=settings.circuit_breaker_enabled,
            failure_threshold=settings.circuit_breaker_failure_threshold,
            reset_timeout_seconds=settings.circuit_breaker_reset_timeout_seconds,
            half_open_max_calls=settings.circuit_breaker_half_open_max_calls,
        )

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ai-devops-platform",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(self, method: str, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        try:
            response = httpx.request(
                method=method,
                url=url,
                headers=self._headers(),
                params=params,
                timeout=self.timeout,
            )
        except httpx.TimeoutException as exc:
            raise GitHubTimeoutError("GitHub request timed out.") from exc
        except httpx.RequestError as exc:
            raise GitHubServiceError("GitHub request failed.") from exc

        if response.status_code == 401:
            raise GitHubAuthError("GitHub authentication failed.")
        if response.status_code == 403:
            if response.headers.get("x-ratelimit-remaining") == "0":
                raise GitHubRateLimitError("GitHub API rate limit exceeded. Please try again later.")
            raise GitHubServiceError("GitHub request forbidden.")
        if response.status_code == 404:
            raise GitHubNotFoundError(f"GitHub resource not found: {path}")
        if response.status_code >= 400:
            raise GitHubServiceError(f"GitHub API error: {response.status_code}")

        try:
            return response.json()
        except ValueError as exc:
            raise GitHubServiceError("GitHub returned malformed data.") from exc

    async def _request_async_once(self, method: str, path: str, params: dict[str, Any] | None = None) -> Any:
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(timeout=self.timeout, limits=self.limits)
        url = f"{self.base_url}{path}"
        try:
            response = await self._async_client.request(
                method=method,
                url=url,
                headers=self._headers(),
                params=params,
            )
        except httpx.TimeoutException as exc:
            raise GitHubTimeoutError("GitHub request timed out.") from exc
        except httpx.RequestError as exc:
            raise GitHubServiceError("GitHub request failed.") from exc

        if response.status_code == 401:
            raise GitHubAuthError("GitHub authentication failed.")
        if response.status_code == 403:
            if response.headers.get("x-ratelimit-remaining") == "0":
                raise GitHubRateLimitError("GitHub API rate limit exceeded. Please try again later.")
            raise GitHubServiceError("GitHub request forbidden.")
        if response.status_code == 429:
            raise GitHubRateLimitError("GitHub API rate limit exceeded. Please try again later.")
        if response.status_code == 404:
            raise GitHubNotFoundError(f"GitHub resource not found: {path}")
        if response.status_code >= 400:
            if response.status_code >= 500:
                raise GitHubHTTPError(f"GitHub API error: {response.status_code}", response.status_code)
            raise GitHubServiceError(f"GitHub API error: {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise GitHubServiceError("GitHub returned malformed data.") from exc

    async def _request_async(self, method: str, path: str, params: dict[str, Any] | None = None) -> Any:
        async def operation():
            await self.circuit_breaker.before_call()
            try:
                result = await self._request_async_once(method, path, params)
            except Exception as error:
                await self.circuit_breaker.record_failure(error)
                raise
            await self.circuit_breaker.record_success()
            return result

        def log_retry(attempt: int, error: BaseException) -> None:
            logger.warning(
                "github_retry operation=%s path=%s attempt=%s error=%s",
                method,
                path,
                attempt,
                type(error).__name__,
            )

        try:
            return await bounded_retry(
                operation,
                max_retries=self.max_retries,
                base_delay=self.retry_base_delay,
                max_delay=self.retry_max_delay,
                on_retry=log_retry,
            )
        except Exception as error:
            if is_retryable(error):
                logger.error("github_retry_exhausted operation=%s path=%s error=%s", method, path, type(error).__name__)
            raise

    async def aclose(self) -> None:
        if self._async_client is not None:
            await self._async_client.aclose()
            self._async_client = None

    async def aget_repository(self, owner: str, repo: str) -> dict[str, Any]:
        return await self._request_async("GET", f"/repos/{owner}/{repo}")

    async def aget_commits(self, owner: str, repo: str, page: int = 1, per_page: int = 30) -> list[dict[str, Any]]:
        return await self._request_async("GET", f"/repos/{owner}/{repo}/commits", params={"page": page, "per_page": per_page})

    async def aget_pull_requests(self, owner: str, repo: str, state: str = "open", page: int = 1, per_page: int = 30) -> list[dict[str, Any]]:
        return await self._request_async("GET", f"/repos/{owner}/{repo}/pulls", params={"state": state, "page": page, "per_page": per_page})

    async def aget_issues(self, owner: str, repo: str, state: str = "open", page: int = 1, per_page: int = 30) -> list[dict[str, Any]]:
        return await self._request_async("GET", f"/repos/{owner}/{repo}/issues", params={"state": state, "page": page, "per_page": per_page})

    async def aget_contents(self, owner: str, repo: str, path: str = "", page: int = 1, per_page: int = 30) -> list[dict[str, Any]] | dict[str, Any]:
        params = {"page": page, "per_page": per_page}
        endpoint = f"/repos/{owner}/{repo}/contents/{path}" if path else f"/repos/{owner}/{repo}/contents"
        return await self._request_async("GET", endpoint, params=params)

    def get_repository(self, owner: str, repo: str) -> dict[str, Any]:
        return self._request("GET", f"/repos/{owner}/{repo}")

    def get_commits(self, owner: str, repo: str, page: int = 1, per_page: int = 30) -> list[dict[str, Any]]:
        return self._request("GET", f"/repos/{owner}/{repo}/commits", params={"page": page, "per_page": per_page})

    def get_pull_requests(self, owner: str, repo: str, state: str = "open", page: int = 1, per_page: int = 30) -> list[dict[str, Any]]:
        return self._request("GET", f"/repos/{owner}/{repo}/pulls", params={"state": state, "page": page, "per_page": per_page})

    def get_issues(self, owner: str, repo: str, state: str = "open", page: int = 1, per_page: int = 30) -> list[dict[str, Any]]:
        return self._request("GET", f"/repos/{owner}/{repo}/issues", params={"state": state, "page": page, "per_page": per_page})

    def get_contents(self, owner: str, repo: str, path: str = "", page: int = 1, per_page: int = 30) -> list[dict[str, Any]] | dict[str, Any]:
        params = {"page": page, "per_page": per_page}
        if path:
            return self._request("GET", f"/repos/{owner}/{repo}/contents/{path}", params=params)
        return self._request("GET", f"/repos/{owner}/{repo}/contents", params=params)
