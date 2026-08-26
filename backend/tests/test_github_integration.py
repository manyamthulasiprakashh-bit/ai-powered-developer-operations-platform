from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.routes.github import get_github_service
from app.core.exceptions import GitHubAuthError, GitHubNotFoundError, GitHubRateLimitError, GitHubServiceError
from app.integrations.github.client import GitHubClient
from app.main import app
from app.services.github_service import GitHubService


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
            {"name": "README.md", "path": "README.md", "type": "file", "size": 123, "url": f"https://api.github.com/repos/{owner}/{repo}/contents/README.md"}
        ]


class RateLimitClient:
    def get_repository(self, owner, repo):
        raise GitHubRateLimitError("GitHub API rate limit exceeded. Please try again later.")


class NotFoundClient:
    def get_repository(self, owner, repo):
        raise GitHubNotFoundError(f"GitHub repository '{owner}/{repo}' was not found.")


class AuthClient:
    def get_repository(self, owner, repo):
        raise GitHubAuthError("GitHub authentication failed.")


class TimeoutClient:
    def get_repository(self, owner, repo):
        raise TimeoutError("GitHub request timed out.")


class InvalidResponseClient:
    def get_repository(self, owner, repo):
        return {"unexpected": "shape"}


def test_github_client_uses_default_api_url():
    client = GitHubClient()

    assert client.base_url == "https://api.github.com"


def test_repository_service_returns_structured_data():
    service = GitHubService(client=FakeClient())

    result = service.get_repository("microsoft", "vscode")

    assert result.name == "vscode"
    assert result.full_name == "microsoft/vscode"
    assert result.language == "Python"
    assert result.stars == 42


def test_repository_service_raises_not_found():
    service = GitHubService(client=NotFoundClient())

    with pytest.raises(GitHubNotFoundError):
        service.get_repository("owner", "missing")


def test_repository_service_raises_rate_limit():
    service = GitHubService(client=RateLimitClient())

    with pytest.raises(GitHubRateLimitError):
        service.get_repository("owner", "repo")


def test_repository_service_raises_auth_error():
    service = GitHubService(client=AuthClient())

    with pytest.raises(GitHubAuthError):
        service.get_repository("owner", "repo")


def test_repository_service_raises_timeout():
    service = GitHubService(client=TimeoutClient())

    with pytest.raises(TimeoutError):
        service.get_repository("owner", "repo")


def test_repository_service_rejects_invalid_github_response():
    service = GitHubService(client=InvalidResponseClient())

    with pytest.raises(GitHubServiceError, match="GitHub returned invalid data"):
        service.get_repository("owner", "repo")


def test_commits_endpoint_returns_paginated_data():
    app.dependency_overrides[get_github_service] = lambda: GitHubService(client=FakeClient())
    client = TestClient(app)

    response = client.get("/api/github/repositories/microsoft/vscode/commits?page=1&per_page=20")

    assert response.status_code == 200
    assert response.json()[0]["sha"] == "abc123"
    app.dependency_overrides.clear()


def test_pull_requests_endpoint_returns_data():
    app.dependency_overrides[get_github_service] = lambda: GitHubService(client=FakeClient())
    client = TestClient(app)

    response = client.get("/api/github/repositories/microsoft/vscode/pull-requests?state=open")

    assert response.status_code == 200
    assert response.json()[0]["title"] == "Add feature"
    app.dependency_overrides.clear()


def test_repository_endpoint_maps_timeout_to_gateway_timeout():
    app.dependency_overrides[get_github_service] = lambda: GitHubService(client=TimeoutClient())

    response = TestClient(app).get("/api/github/repositories/owner/repo")

    assert response.status_code == 504
    assert response.json() == {"detail": "GitHub request timed out."}
    app.dependency_overrides.clear()


def test_commits_endpoint_maps_rate_limit_to_too_many_requests():
    class RateLimitedCommitsClient(FakeClient):
        def get_commits(self, owner, repo, page=1, per_page=30):
            raise GitHubRateLimitError("GitHub API rate limit exceeded. Please try again later.")

    app.state.rate_limiter.reset()
    app.dependency_overrides[get_github_service] = lambda: GitHubService(client=RateLimitedCommitsClient())

    response = TestClient(app).get("/api/github/repositories/owner/repo/commits")

    assert response.status_code == 429
    assert response.json()["detail"] == "GitHub API rate limit exceeded. Please try again later."
    app.dependency_overrides.clear()


def test_issues_endpoint_returns_data():
    app.dependency_overrides[get_github_service] = lambda: GitHubService(client=FakeClient())
    client = TestClient(app)

    response = client.get("/api/github/repositories/microsoft/vscode/issues?state=open")

    assert response.status_code == 200
    assert response.json()[0]["title"] == "Bug report"
    app.dependency_overrides.clear()


class MixedIssueClient:
    def get_issues(self, owner, repo, state="open", page=1, per_page=30):
        return [
            {
                "number": 1,
                "title": "Issue only",
                "state": "open",
                "user": {"login": "octocat"},
                "labels": [{"name": "bug"}],
                "created_at": "2024-02-01T00:00:00Z",
                "updated_at": "2024-02-02T00:00:00Z",
                "html_url": f"https://github.com/{owner}/{repo}/issues/1",
            },
            {
                "number": 2,
                "title": "PR disguised as issue",
                "state": "open",
                "user": {"login": "octocat"},
                "pull_request": {"url": "https://api.github.com/repos/microsoft/vscode/pulls/2"},
                "created_at": "2024-02-01T00:00:00Z",
                "updated_at": "2024-02-02T00:00:00Z",
                "html_url": f"https://github.com/{owner}/{repo}/pull/2",
            },
        ]


def test_issues_endpoint_excludes_pull_requests_from_issue_list():
    app.dependency_overrides[get_github_service] = lambda: GitHubService(client=MixedIssueClient())
    client = TestClient(app)

    response = client.get("/api/github/repositories/microsoft/vscode/issues?state=open")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["title"] == "Issue only"
    assert payload[0]["url"] == "https://github.com/microsoft/vscode/issues/1"
    app.dependency_overrides.clear()


def test_contents_endpoint_returns_data():
    app.dependency_overrides[get_github_service] = lambda: GitHubService(client=FakeClient())
    client = TestClient(app)

    response = client.get("/api/github/repositories/microsoft/vscode/contents")

    assert response.status_code == 200
    assert response.json()[0]["name"] == "README.md"
    app.dependency_overrides.clear()


def test_repository_not_found_returns_404():
    app.dependency_overrides[get_github_service] = lambda: GitHubService(client=NotFoundClient())
    client = TestClient(app)

    response = client.get("/api/github/repositories/owner/missing")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
    app.dependency_overrides.clear()
