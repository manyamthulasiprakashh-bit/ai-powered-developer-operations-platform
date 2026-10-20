from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
NGINX_TEMPLATE = REPO_ROOT / "frontend" / "nginx.conf.template"
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"


def test_nginx_template_uses_configurable_upstream_and_proxy_headers():
    template = NGINX_TEMPLATE.read_text(encoding="utf-8")

    assert "proxy_pass ${BACKEND_UPSTREAM};" in template
    assert "http://backend:8000" not in template
    assert "proxy_set_header Host $proxy_host;" in template
    assert "proxy_ssl_server_name on;" in template


def test_nginx_template_preserves_owner_auth_and_server_side_api_key():
    template = NGINX_TEMPLATE.read_text(encoding="utf-8")

    assert 'auth_basic "AI DevOps Demo (owner access)";' in template
    assert "auth_basic_user_file /etc/nginx/auth/htpasswd;" in template
    assert "proxy_set_header X-API-Key ${API_KEY};" in template
    assert 'proxy_set_header Authorization "";' in template
    assert "VITE_" not in template


def test_compose_pins_local_upstream_without_changing_same_origin_build():
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    frontend = compose["services"]["frontend"]

    assert frontend["environment"]["BACKEND_UPSTREAM"] == "http://backend:8000"
    assert frontend["environment"]["API_KEY"] == "${API_KEY:-}"
    assert frontend["build"]["args"]["VITE_API_BASE_URL"] == "${VITE_API_BASE_URL:-/}"
    assert "VITE_BACKEND_UPSTREAM" not in frontend["build"]["args"]
    assert "VITE_BACKEND_UPSTREAM" not in frontend["environment"]
