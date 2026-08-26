import pytest
from fastapi.testclient import TestClient

from app.api.routes.github import get_github_service
from app.core.config import Settings
from app.core.exceptions import GitHubServiceError
from app.core.security import InMemoryRateLimiter, redact_sensitive
from app.main import app


def test_security_headers_are_present_on_health_response():
    response = TestClient(app).get("/api/health")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert "Strict-Transport-Security" not in response.headers


def test_request_id_is_generated_and_supplied_id_is_preserved(caplog):
    client = TestClient(app)

    with caplog.at_level("INFO"):
        generated = client.get("/api/health")
        supplied = client.get("/api/health", headers={"X-Request-ID": "test-request-123"})

    assert len(generated.headers["X-Request-ID"]) > 10
    assert supplied.headers["X-Request-ID"] == "test-request-123"
    assert any(getattr(record, "request_id", None) == "test-request-123" for record in caplog.records)


def test_cors_allows_configured_origin_and_rejects_other_origins():
    client = TestClient(app)

    allowed = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    rejected = client.get("/api/health", headers={"Origin": "https://attacker.example"})

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in rejected.headers


def test_production_cors_requires_https_origins(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://frontend.example.com")

    settings = Settings()

    assert settings.cors_allowed_origins == ["https://frontend.example.com"]

    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://frontend.example.com")
    with pytest.raises(ValueError, match="must use HTTPS"):
        Settings()


def test_malformed_cors_origin_is_rejected():
    with pytest.raises(ValueError, match="absolute HTTP"):
        Settings(CORS_ALLOWED_ORIGINS="not-an-origin")


def test_rate_limiter_enforces_and_resets_window():
    limiter = InMemoryRateLimiter(max_requests=2, window_seconds=10)

    assert limiter.allow("client", now=100) == (True, 0)
    assert limiter.allow("client", now=101) == (True, 0)
    assert limiter.allow("client", now=102)[0] is False
    assert limiter.allow("client", now=111) == (True, 0)


def test_health_endpoint_is_exempt_from_rate_limiting():
    original = app.state.rate_limiter
    app.state.rate_limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
    try:
        client = TestClient(app)
        assert client.get("/").status_code == 200
        limited = client.get("/")
        assert limited.status_code == 429
        assert limited.headers["Retry-After"]
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/ready").status_code == 200
    finally:
        app.state.rate_limiter = original


def test_sensitive_values_are_redacted():
    message = "token=abc123 authorization=Bearer-secret password=hunter2"

    redacted = redact_sensitive(message)

    assert "abc123" not in redacted
    assert "Bearer-secret" not in redacted
    assert "hunter2" not in redacted
    assert redacted.count("[REDACTED]") == 3


def test_upstream_error_response_does_not_expose_exception_detail():
    class LeakyClient:
        def get_repository(self, owner, repo):
            raise GitHubServiceError("token=super-secret")

    from app.services.github_service import GitHubService

    app.dependency_overrides[get_github_service] = lambda: GitHubService(client=LeakyClient())
    try:
        response = TestClient(app).get("/api/github/repositories/owner/repo")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert "super-secret" not in response.text
    assert response.json()["detail"] == "GitHub service unavailable."
    assert response.json()["error"] == "upstream_unavailable"
    assert response.json()["retryable"] is True
