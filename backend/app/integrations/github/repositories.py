from __future__ import annotations

from typing import Any

from app.integrations.github.client import GitHubClient


class GitHubRepositoryClient:
    def __init__(self, client: GitHubClient | None = None) -> None:
        self.client = client or GitHubClient()

    def get_repository(self, owner: str, repo: str) -> dict[str, Any]:
        return self.client.get_repository(owner, repo)
