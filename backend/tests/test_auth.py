from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.routes.github import get_github_service
from app.core.config import get_settings
from app.db.session import get_db
from app.main import app
from app.services.github_service import GitHubService

PROTECTED_REQUESTS = [
    ("post", "/api/github/repositories/microsoft/vscode/analysis"),
    ("get", "/api/analyses"),
    ("get", "/api/analyses/1"),
    ("get", "/api/statistics"),
    ("get", "/api/documents"),
    ("get", "/api/documents/1"),
    ("get", "/api/documents/1/audit"),
    ("post", "/api/documents/1/decisions"),
]


class FakeClient:
    def get_repository(self, owner, repo):
        return {
            "name": repo,
            "full_name": f"{owner}/{repo}",
            "owner": {"login": owner},
            "private": False,
            "default_branch": "main",
            "language": "Python",
            "stargazers_count": 1,
            "forks_count": 0,
            "open_issues_count": 0,
            "html_url": f"https://github.com/{owner}/{repo}",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-02-01T00:00:00Z",
        }

    def get_commits(self, owner, repo, page=1, per_page=30):
        return []

    def get_pull_requests(self, owner, repo, state="open", page=1, per_page=30):
        return []

    def get_issues(self, owner, repo, state="open", page=1, per_page=30):
        return []

    def get_contents(self, owner, repo, path="", page=1, per_page=30):
        return [{"name": "README.md", "path": "README.md", "type": "file", "size": 1, "url": None}]


@pytest.mark.parametrize("method,path", PROTECTED_REQUESTS)
def test_protected_endpoints_reject_missing_key(method, path):
    response = getattr(TestClient(app), method)(path)

    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"
    assert response.json()["detail"] == "Unauthorized."


@pytest.mark.parametrize("method,path", PROTECTED_REQUESTS)
def test_protected_endpoints_reject_invalid_key(method, path):
    response = getattr(TestClient(app, headers={"X-API-Key": "wrong-key"}), method)(path)

    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


def test_supplied_key_is_never_echoed_in_the_response():
    response = TestClient(app, headers={"X-API-Key": "wrong-key"}).get("/api/statistics")

    assert "wrong-key" not in response.text


def test_health_and_readiness_remain_public(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        client = TestClient(app)
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/ready").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_valid_key_allows_statistics(db_session, auth_headers):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        response = TestClient(app, headers=auth_headers).get("/api/statistics")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["total_analyses"] == 0


def test_valid_key_preserves_analysis_response_contract(db_session, auth_headers):
    app.dependency_overrides[get_github_service] = lambda: GitHubService(client=FakeClient())
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        response = TestClient(app, headers=auth_headers).post(
            "/api/github/repositories/microsoft/vscode/analysis"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert set(response.json()) == {"owner", "repository", "analyzed_at", "summary", "metrics", "findings"}


def test_protected_endpoints_fail_closed_when_key_not_configured(monkeypatch):
    monkeypatch.setenv("API_KEY", "")
    get_settings.cache_clear()
    try:
        response = TestClient(app).get("/api/statistics")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 503
    assert response.json()["error"] == "authentication_not_configured"
    assert response.json()["detail"] == "Authentication is not configured."


def test_valid_supplied_key_does_not_bypass_unconfigured_server(monkeypatch):
    monkeypatch.setenv("API_KEY", "")
    get_settings.cache_clear()
    try:
        response = TestClient(app, headers={"X-API-Key": "anything"}).get("/api/analyses")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 503
    assert response.json()["error"] == "authentication_not_configured"
