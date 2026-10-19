from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.routes.github import get_github_service
from app.db.session import get_db
from app.main import app
from app.services.github_service import GitHubService

ANALYSIS_KEYS = {"owner", "repository", "analyzed_at", "summary", "metrics", "findings"}


class FakeClient:
    def get_repository(self, owner, repo):
        return {
            "name": repo,
            "full_name": f"{owner}/{repo}",
            "owner": {"login": owner},
            "description": "Example repo",
            "private": False,
            "default_branch": "main",
            "language": "Python",
            "stargazers_count": 42,
            "forks_count": 7,
            "open_issues_count": 3,
            "html_url": f"https://github.com/{owner}/{repo}",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-02-01T00:00:00Z",
        }

    def get_commits(self, owner, repo, page=1, per_page=30):
        return [
            {
                "sha": "abc123",
                "commit": {"message": "Initial commit", "author": {"date": "2024-02-01T00:00:00Z"}},
                "author": {"login": "octocat"},
                "html_url": f"https://github.com/{owner}/{repo}/commit/abc123",
            }
        ]

    def get_pull_requests(self, owner, repo, state="open", page=1, per_page=30):
        return [
            {
                "number": 1,
                "title": "Add feature",
                "state": state,
                "user": {"login": "octocat"},
                "created_at": "2024-02-01T00:00:00Z",
                "updated_at": "2024-02-02T00:00:00Z",
                "merged_at": None,
                "html_url": f"https://github.com/{owner}/{repo}/pull/1",
            }
        ]

    def get_issues(self, owner, repo, state="open", page=1, per_page=30):
        return [
            {
                "number": 2,
                "title": "Bug report",
                "state": state,
                "user": {"login": "octocat"},
                "labels": [{"name": "bug"}],
                "created_at": "2024-02-01T00:00:00Z",
                "updated_at": "2024-02-02T00:00:00Z",
                "html_url": f"https://github.com/{owner}/{repo}/issues/2",
            }
        ]

    def get_contents(self, owner, repo, path="", page=1, per_page=30):
        return [
            {
                "name": "README.md",
                "path": "README.md",
                "type": "file",
                "size": 123,
                "url": f"https://api.github.com/repos/{owner}/{repo}/contents/README.md",
            }
        ]


def test_analysis_flow_persists_and_is_visible_in_history_and_statistics(db_session, auth_headers):
    app.dependency_overrides[get_github_service] = lambda: GitHubService(client=FakeClient())
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        client = TestClient(app, headers=auth_headers)

        analysis_response = client.post("/api/github/repositories/microsoft/vscode/analysis")
        assert analysis_response.status_code == 200
        analysis = analysis_response.json()
        assert set(analysis) == ANALYSIS_KEYS
        assert analysis["owner"] == "microsoft"
        assert analysis["repository"] == "vscode"

        history_response = client.get("/api/analyses?limit=5&offset=0")
        assert history_response.status_code == 200
        history = history_response.json()
        assert history["total"] == 1
        assert history["limit"] == 5
        assert history["offset"] == 0
        assert len(history["items"]) == 1
        item = history["items"][0]
        assert item["owner"] == "microsoft"
        assert item["repository"] == "vscode"
        assert item["summary"] == analysis["summary"]

        detail_response = client.get(f"/api/analyses/{item['id']}")
        assert detail_response.status_code == 200
        detail = detail_response.json()
        assert detail["metrics"] == analysis["metrics"]
        assert detail["findings"] == analysis["findings"]

        statistics_response = client.get("/api/statistics")
        assert statistics_response.status_code == 200
        statistics = statistics_response.json()
        assert statistics["total_analyses"] == 1
        assert statistics["distinct_owners"] == 1
        assert statistics["distinct_repositories"] == 1
        assert statistics["analyses_last_7_days"] == 1
        assert statistics["analyses_last_30_days"] == 1
        assert statistics["latest_analyzed_at"] is not None
    finally:
        app.dependency_overrides.clear()
