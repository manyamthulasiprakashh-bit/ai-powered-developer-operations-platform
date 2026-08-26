import json
import logging

from fastapi.testclient import TestClient

from app.api.routes.github import get_github_service
from app.core.exceptions import GitHubServiceError
from app.core.metrics import metrics
from app.core.logging import JsonFormatter
from app.main import app
from app.integrations.github.client import GitHubClient
from app.services.github_service import GitHubService


class ObservableClient:
    def __init__(self):
        self.calls = 0

    async def aget_repository(self, owner, repo):
        self.calls += 1
        return {
            "name": repo,
            "full_name": f"{owner}/{repo}",
            "owner": {"login": owner},
            "private": False,
            "default_branch": "main",
            "html_url": f"https://github.com/{owner}/{repo}",
        }


def setup_function():
    metrics.reset()


def test_json_formatter_is_structured_and_does_not_include_secret_values():
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "token=%s", ("secret-value",), None)
    record.request_id = "request-1"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["request_id"] == "request-1"
    assert "secret-value" not in JsonFormatter().format(record)


def test_metrics_endpoint_reports_http_counts_and_duration():
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    payload = TestClient(app).get("/metrics").json()
    assert payload["http_requests_total"]["value"] >= 2
    assert payload["http_request_duration_seconds"]["count"] >= 1
    assert "request_id" not in str(payload)


def test_health_aliases_are_lightweight_and_available():
    client = TestClient(app)

    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/ready").json()["status"] == "ready"


def test_http_error_increments_error_counter():
    response = TestClient(app).get("/api/github/repositories/owner/repo/commits?page=0")

    assert response.status_code == 422
    assert metrics.snapshot()["http_errors_total"]["value"] >= 1


def test_github_and_cache_metrics_are_recorded():
    class CountingClient(GitHubClient):
        def __init__(self):
            super().__init__(base_url="https://github.example")
            self.calls = 0

        async def _request_async_once(self, method, path, params=None):
            self.calls += 1
            return {
                "name": "repo",
                "full_name": "owner/repo",
                "owner": {"login": "owner"},
                "private": False,
                "default_branch": "main",
                "html_url": "https://github.com/owner/repo",
            }

    client = CountingClient()
    service = GitHubService(client=client)
    app.dependency_overrides[get_github_service] = lambda: service
    try:
        api_client = TestClient(app)
        assert api_client.get("/api/github/repositories/owner/repo").status_code == 200
        assert api_client.get("/api/github/repositories/owner/repo").status_code == 200
    finally:
        app.dependency_overrides.clear()

    snapshot = metrics.snapshot()
    assert snapshot["github_requests_total"]["value"] == 1
    assert snapshot["github_request_duration_seconds"]["count"] == 1
    assert snapshot["cache_misses_total"]["value"] == 1
    assert snapshot["cache_hits_total"]["value"] == 1


def test_github_failure_metric_is_recorded_without_secret_data():
    class FailingClient(GitHubClient):
        def __init__(self):
            super().__init__(base_url="https://github.example")
            self.max_retries = 0

        async def _request_async_once(self, method, path, params=None):
            raise GitHubServiceError("token=do-not-log")

    app.dependency_overrides[get_github_service] = lambda: GitHubService(client=FailingClient())
    try:
        response = TestClient(app).get("/api/github/repositories/owner/repo")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert metrics.snapshot()["github_failures_total"]["value"] >= 1
    assert "do-not-log" not in response.text