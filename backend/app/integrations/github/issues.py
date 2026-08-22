from __future__ import annotations

from app.integrations.github.client import GitHubClient


class GitHubIssuesClient:
    def __init__(self, client: GitHubClient | None = None) -> None:
        self.client = client or GitHubClient()

    def get_issues(self, owner: str, repo: str, state: str = "open", page: int = 1, per_page: int = 30):
        return self.client.get_issues(owner, repo, state=state, page=page, per_page=per_page)
