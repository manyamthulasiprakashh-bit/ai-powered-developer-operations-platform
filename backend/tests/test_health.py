import importlib

from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "service" in response.json()


def test_readiness_endpoint_is_deterministic():
    response = TestClient(app).get("/api/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "ai-devops-platform",
        "checks": {"configuration": "ok"},
    }


def test_invalid_pagination_returns_safe_validation_error():
    response = TestClient(app).get("/api/github/repositories/owner/repo/commits?page=0")

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid request parameters."
    assert response.json()["error"] == "invalid_request"
    assert response.json()["retryable"] is False


def test_platform_config_reads_port_and_cors_origins(monkeypatch):
    monkeypatch.setenv("PORT", "9090")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://frontend.example.com,https://admin.example.com")

    import app.core.config as config_module

    importlib.reload(config_module)
    settings = config_module.Settings()

    assert settings.backend_port == 9090
    assert settings.cors_allowed_origins == ["https://frontend.example.com", "https://admin.example.com"]
