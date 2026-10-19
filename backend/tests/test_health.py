import importlib

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_db
from app.main import app


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "service" in response.json()


def test_readiness_endpoint_is_deterministic(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        response = TestClient(app).get("/api/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "ai-devops-platform",
        "checks": {"configuration": "ok", "database": "ok"},
    }


def test_readiness_returns_safe_503_when_database_is_unavailable():
    class UnavailableSession:
        def execute(self, *args, **kwargs):
            raise OperationalError(
                "SELECT 1 FROM analyses WHERE password=super-secret",
                {"password": "super-secret"},
                Exception("database unavailable"),
            )

        def close(self):
            return None

    app.dependency_overrides[get_db] = lambda: UnavailableSession()
    try:
        response = TestClient(app).get("/api/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["database"] == "unavailable"
    assert "super-secret" not in response.text
    assert "SELECT" not in response.text


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
