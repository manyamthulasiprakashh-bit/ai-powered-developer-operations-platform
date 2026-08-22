from __future__ import annotations

from app.integrations.github.client import GitHubClient


class GitHubCommitsClient:
    def __init__(self, client: GitHubClient | None = None) -> None:
        self.client = client or GitHubClient()

    def get_commits(self, owner: str, repo: str, page: int = 1, per_page: int = 30):
        return self.client.get_commits(owner, repo, page=page, per_page=per_page)
