from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCUMENT_ENV_VARS = (
    "DOCUMENT_MAX_SIZE_BYTES",
    "DOCUMENT_MAX_TEXT_CHARS",
    "DOCUMENT_PREVIEW_CHARS",
    "DOCUMENT_MULTIPART_OVERHEAD_BYTES",
    "DOCUMENT_ALLOWED_CONTENT_TYPES",
    "DOCUMENT_ALLOWED_EXTENSIONS",
)


@pytest.fixture(autouse=True)
def _clean_document_env(monkeypatch):
    for name in DOCUMENT_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def _settings(**overrides):
    return Settings(_env_file=None, **overrides)


def test_default_document_limits_and_derived_request_cap():
    settings = _settings()

    assert settings.document_max_size_bytes == 1_048_576
    assert settings.document_max_text_chars == 20_000
    assert settings.document_preview_chars == 500
    assert settings.document_multipart_overhead_bytes == 65_536
    assert settings.document_max_request_bytes == 1_114_112


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("document_max_size_bytes", 0),
        ("document_max_size_bytes", -1),
        ("document_max_size_bytes", 16_777_217),
        ("document_max_text_chars", 0),
        ("document_max_text_chars", 200_001),
        ("document_preview_chars", 0),
        ("document_preview_chars", 2_001),
        ("document_multipart_overhead_bytes", -1),
        ("document_multipart_overhead_bytes", 1_048_577),
    ],
)
def test_document_limits_outside_bounds_are_rejected(field, value):
    with pytest.raises(ValidationError):
        _settings(**{field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("document_max_size_bytes", 1),
        ("document_max_size_bytes", 16_777_216),
        ("document_max_text_chars", 200_000),
        ("document_preview_chars", 2_000),
        ("document_multipart_overhead_bytes", 0),
    ],
)
def test_document_limit_boundaries_are_accepted(field, value):
    settings = _settings(**{field: value})

    assert getattr(settings, field) == value


def test_non_numeric_document_limit_is_rejected(monkeypatch):
    monkeypatch.setenv("DOCUMENT_MAX_SIZE_BYTES", "not-a-number")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def _parse_nginx_size(raw: str) -> int:
    match = re.fullmatch(r"(\d+)([kKmMgG]?)", raw)
    assert match, raw
    multipliers = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3}
    return int(match.group(1)) * multipliers[match.group(2).lower()]


def test_nginx_client_max_body_size_exceeds_application_cap():
    template = (REPO_ROOT / "frontend" / "nginx.conf.template").read_text(encoding="utf-8")
    match = re.search(r"client_max_body_size\s+([0-9]+[kKmMgG]?);", template)
    assert match, "client_max_body_size must be explicit in the nginx template"

    assert _parse_nginx_size(match.group(1)) > Settings(_env_file=None).document_max_request_bytes
