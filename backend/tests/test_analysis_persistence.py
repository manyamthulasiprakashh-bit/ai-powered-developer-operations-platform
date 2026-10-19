from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.routes.github import get_github_service
from app.core.exceptions import GitHubNotFoundError
from app.db.session import get_db
from app.main import app
from app.models import Analysis
from app.services.github_service import GitHubService

ANALYSIS_KEYS = {"owner", "repository", "analyzed_at", "summary", "metrics", "findings"}
EXPECTED_METRICS = {
    "commit_count": 1,
    "open_issue_count": 1,
    "open_pull_request_count": 1,
    "root_content_count": 1,
    "has_readme": True,
    "has_ci_configuration": False,
}


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


def _override_dependencies(db_session, client):
    app.dependency_overrides[get_github_service] = lambda: GitHubService(client=client)
    app.dependency_overrides[get_db] = lambda: db_session


def test_successful_analysis_is_persisted_with_unchanged_response_shape(db_session, auth_headers):
    _override_dependencies(db_session, FakeClient())
    try:
        response = TestClient(app, headers=auth_headers).post("/api/github/repositories/microsoft/vscode/analysis")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == ANALYSIS_KEYS
    assert payload["metrics"] == EXPECTED_METRICS
    assert payload["findings"]

    stored = db_session.execute(select(Analysis)).scalars().all()
    assert len(stored) == 1
    record = stored[0]
    assert record.id is not None
    assert record.owner == "microsoft"
    assert record.repository == "vscode"
    assert record.summary == payload["summary"]
    assert record.metrics == EXPECTED_METRICS
    assert record.findings == payload["findings"]
    assert record.created_at is not None


def test_analysis_service_failure_persists_nothing(db_session, auth_headers):
    class NotFoundClient(FakeClient):
        def get_repository(self, owner, repo):
            raise GitHubNotFoundError(f"GitHub repository '{owner}/{repo}' was not found.")

    _override_dependencies(db_session, NotFoundClient())
    try:
        response = TestClient(app, headers=auth_headers).post("/api/github/repositories/owner/missing/analysis")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert db_session.execute(select(Analysis)).scalars().all() == []


def test_persistence_failure_returns_safe_error_and_rolls_back(db_session, monkeypatch, auth_headers):
    rollback_calls = {"count": 0}
    original_rollback = db_session.rollback

    def tracked_rollback():
        rollback_calls["count"] += 1
        return original_rollback()

    def failing_commit():
        raise RuntimeError("connection to database failed password=super-secret")

    monkeypatch.setattr(db_session, "commit", failing_commit)
    monkeypatch.setattr(db_session, "rollback", tracked_rollback)

    _override_dependencies(db_session, FakeClient())
    try:
        response = TestClient(app, headers=auth_headers).post("/api/github/repositories/microsoft/vscode/analysis")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error."
    assert "super-secret" not in response.text
    assert "password" not in response.text.lower()
    assert rollback_calls["count"] == 1
