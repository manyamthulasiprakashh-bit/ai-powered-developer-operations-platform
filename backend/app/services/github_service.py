from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import (
    GitHubAuthError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubServiceError,
    GitHubTimeoutError,
)
from app.integrations.github.client import GitHubClient
from app.schemas.github import CommitSummary, IssueSummary, PullRequestSummary, RepositoryContent, RepositorySummary


class GitHubService:
    def __init__(self, client: GitHubClient | None = None) -> None:
        self.client = client or GitHubClient()

    def _normalize_repository(self, payload: dict[str, Any]) -> RepositorySummary:
        return RepositorySummary(
            name=payload.get("name"),
            full_name=payload.get("full_name"),
            owner=(payload.get("owner") or {}).get("login"),
            description=payload.get("description"),
            private=payload.get("private", False),
            default_branch=payload.get("default_branch", "main"),
            language=payload.get("language"),
            stargazers_count=payload.get("stargazers_count", 0),
            forks_count=payload.get("forks_count", 0),
            open_issues_count=payload.get("open_issues_count", 0),
            html_url=payload.get("html_url"),
            created_at=payload.get("created_at"),
            updated_at=payload.get("updated_at"),
        )

    def _normalize_commit(self, payload: dict[str, Any]) -> CommitSummary:
        author = payload.get("author") or {}
        commit = payload.get("commit") or {}
        author_data = commit.get("author") or {}
        return CommitSummary(
            sha=payload.get("sha"),
            short_sha=(payload.get("sha") or "")[:7],
            message=(commit.get("message") or "").strip(),
            author=(author.get("login") if isinstance(author, dict) else None),
            author_email=author_data.get("email"),
            committed_at=author_data.get("date"),
            url=payload.get("html_url"),
        )

    def _normalize_pull_request(self, payload: dict[str, Any]) -> PullRequestSummary:
        user = payload.get("user") or {}
        return PullRequestSummary(
            number=payload.get("number"),
            title=payload.get("title"),
            state=payload.get("state"),
            author=user.get("login"),
            created_at=payload.get("created_at"),
            updated_at=payload.get("updated_at"),
            merged_at=payload.get("merged_at"),
            url=payload.get("html_url"),
        )

    def _normalize_issue(self, payload: dict[str, Any]) -> IssueSummary:
        user = payload.get("user") or {}
        labels = [item.get("name") for item in payload.get("labels", []) if isinstance(item, dict)]
        return IssueSummary(
            number=payload.get("number"),
            title=payload.get("title"),
            state=payload.get("state"),
            author=user.get("login"),
            labels=labels,
            created_at=payload.get("created_at"),
            updated_at=payload.get("updated_at"),
            url=payload.get("html_url"),
        )

    def _normalize_content(self, payload: dict[str, Any]) -> RepositoryContent:
        return RepositoryContent(
            name=payload.get("name"),
            path=payload.get("path"),
            type=payload.get("type"),
            size=payload.get("size"),
            url=payload.get("url"),
        )

    def get_repository(self, owner: str, repo: str) -> RepositorySummary:
        try:
            payload = self.client.get_repository(owner, repo)
            return self._normalize_repository(payload)
        except GitHubNotFoundError:
            raise
        except GitHubAuthError:
            raise
        except GitHubRateLimitError:
            raise
        except GitHubTimeoutError:
            raise
        except TimeoutError as exc:
            raise GitHubTimeoutError("GitHub request timed out.") from exc
        except (PydanticValidationError, TypeError, AttributeError) as exc:
            raise GitHubServiceError("GitHub returned invalid data.") from exc
        except GitHubServiceError as exc:
            raise GitHubServiceError(str(exc)) from exc

    def get_commits(self, owner: str, repo: str, page: int = 1, per_page: int = 30) -> list[CommitSummary]:
        try:
            payload = self.client.get_commits(owner, repo, page=page, per_page=per_page)
            return [self._normalize_commit(item) for item in payload]
        except TimeoutError as exc:
            raise GitHubTimeoutError("GitHub request timed out.") from exc
        except (PydanticValidationError, TypeError, AttributeError) as exc:
            raise GitHubServiceError("GitHub returned invalid data.") from exc

    def get_pull_requests(self, owner: str, repo: str, state: str = "open", page: int = 1, per_page: int = 30) -> list[PullRequestSummary]:
        try:
            payload = self.client.get_pull_requests(owner, repo, state=state, page=page, per_page=per_page)
            return [self._normalize_pull_request(item) for item in payload]
        except TimeoutError as exc:
            raise GitHubTimeoutError("GitHub request timed out.") from exc
        except (PydanticValidationError, TypeError, AttributeError) as exc:
            raise GitHubServiceError("GitHub returned invalid data.") from exc

    def get_issues(self, owner: str, repo: str, state: str = "open", page: int = 1, per_page: int = 30) -> list[IssueSummary]:
        try:
            payload = self.client.get_issues(owner, repo, state=state, page=page, per_page=per_page)
            filtered = [item for item in payload if item.get("pull_request") is None]
            return [self._normalize_issue(item) for item in filtered]
        except TimeoutError as exc:
            raise GitHubTimeoutError("GitHub request timed out.") from exc
        except (PydanticValidationError, TypeError, AttributeError) as exc:
            raise GitHubServiceError("GitHub returned invalid data.") from exc

    def get_contents(self, owner: str, repo: str, path: str = "", page: int = 1, per_page: int = 30):
        try:
            payload = self.client.get_contents(owner, repo, path=path, page=page, per_page=per_page)
            if isinstance(payload, list):
                return [self._normalize_content(item) for item in payload]
            return self._normalize_content(payload)
        except TimeoutError as exc:
            raise GitHubTimeoutError("GitHub request timed out.") from exc
        except (PydanticValidationError, TypeError, AttributeError) as exc:
            raise GitHubServiceError("GitHub returned invalid data.") from exc
