from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings
from app.core.exceptions import (
    GitHubAuthError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubServiceError,
    GitHubTimeoutError,
)


class GitHubClient:
    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.github_api_url or "https://api.github.com").rstrip("/")
        self.token = token or settings.github_token
        self.timeout = 15.0

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
