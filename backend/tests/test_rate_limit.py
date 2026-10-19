from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.routes.github import get_github_service
from app.core.security import InMemoryRateLimiter, categorize_request, resolve_client_identity
from app.db.session import get_db
from app.main import app
from app.services.github_service import GitHubService


class RepoClient:
    def get_repository(self, owner, repo):
        return {
            "name": repo,
            "full_name": f"{owner}/{repo}",
            "owner": {"login": owner},
            "private": False,
            "default_branch": "main",
            "html_url": f"https://github.com/{owner}/{repo}",
        }

    def get_commits(self, owner, repo, page=1, per_page=30):
        return []

    def get_pull_requests(self, owner, repo, state="open", page=1, per_page=30):
        return []

    def get_issues(self, owner, repo, state="open", page=1, per_page=30):
        return []

    def get_contents(self, owner, repo, path="", page=1, per_page=30):
        return [{"name": "README.md", "path": "README.md", "type": "file", "size": 1, "url": None}]


def test_repository_paths_normalize_to_a_single_route_category():
    assert categorize_request("GET", "/api/github/repositories/a/b") == categorize_request(
        "GET", "/api/github/repositories/c/d"
    )
    assert categorize_request("GET", "/api/github/repositories/a/b") == "/api/github/repositories/{owner}/{repo}"
    assert categorize_request("GET", "/api/github/repositories/a/b/commits") == "/api/github/repositories/{owner}/{repo}/commits"
    assert categorize_request("POST", "/api/github/repositories/a/b/analysis") == "/api/github/repositories/{owner}/{repo}/analysis"
    assert categorize_request("GET", "/api/analyses/123") == "/api/analyses/{analysis_id}"
    assert categorize_request("GET", "/unmatched/path") == "other"


def test_forwarded_for_is_ignored_without_a_trusted_proxy():
    assert resolve_client_identity("10.0.0.1", "1.2.3.4", []) == "10.0.0.1"
    assert resolve_client_identity("10.0.0.1", "1.2.3.4", ["10.0.0.1"]) == "1.2.3.4"
    assert resolve_client_identity(None, "1.2.3.4", ["10.0.0.1"]) == "unknown"


def test_different_repository_paths_share_one_rate_limit_bucket():
    original = app.state.rate_limiter
    app.state.rate_limiter = InMemoryRateLimiter(max_requests=2, window_seconds=60)
    app.dependency_overrides[get_github_service] = lambda: GitHubService(client=RepoClient())
    try:
        client = TestClient(app)
        assert client.get("/api/github/repositories/a/one").status_code == 200
        assert client.get("/api/github/repositories/b/two").status_code == 200
        third = client.get("/api/github/repositories/c/three")
        assert third.status_code == 429
        assert third.headers["Retry-After"]
    finally:
        app.state.rate_limiter = original
        app.dependency_overrides.clear()


def test_analysis_uses_a_stricter_bucket_across_repositories(db_session, auth_headers):
    original = app.state.analysis_rate_limiter
    app.state.analysis_rate_limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
    app.dependency_overrides[get_github_service] = lambda: GitHubService(client=RepoClient())
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        client = TestClient(app, headers=auth_headers)
        assert client.post("/api/github/repositories/a/one/analysis").status_code == 200
        second = client.post("/api/github/repositories/b/two/analysis")
        assert second.status_code == 429
    finally:
        app.state.analysis_rate_limiter = original
        app.dependency_overrides.clear()
