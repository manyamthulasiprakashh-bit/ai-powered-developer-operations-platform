import importlib

from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "service" in response.json()


def test_platform_config_reads_port_and_cors_origins(monkeypatch):
    monkeypatch.setenv("PORT", "9090")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://frontend.example.com,https://admin.example.com")

    import app.core.config as config_module

    importlib.reload(config_module)
    settings = config_module.Settings()

    assert settings.backend_port == 9090
    assert settings.cors_allowed_origins == ["https://frontend.example.com", "https://admin.example.com"]
