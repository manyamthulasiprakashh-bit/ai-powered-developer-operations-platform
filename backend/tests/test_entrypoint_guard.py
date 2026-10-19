from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parents[2] / "frontend" / "docker-entrypoint-guard.sh"
VALID_KEY = "a" * 64
HTPASSWD_LINE = "owner:$apr1$abc$def\n"


def _run_guard(tmp_path, *, api_key=VALID_KEY, htpasswd=HTPASSWD_LINE, make_dir=False):
    env = dict(os.environ)
    env.pop("API_KEY", None)
    if api_key is not None:
        env["API_KEY"] = api_key

    htpasswd_path = tmp_path / "htpasswd"
    if make_dir:
        htpasswd_path.mkdir()
    elif htpasswd is not None:
        htpasswd_path.write_text(htpasswd, encoding="utf-8")
    env["HTPASSWD_FILE"] = str(htpasswd_path)

    marker = tmp_path / "entrypoint-ran"
    stub = tmp_path / "entrypoint.sh"
    stub.write_text(f'#!/bin/sh\nprintf ran > "{marker}"\n', encoding="utf-8")
    stub.chmod(0o755)
    env["DOCKER_ENTRYPOINT"] = str(stub)

    result = subprocess.run(["sh", str(GUARD)], capture_output=True, text=True, env=env)
    return result, marker


def test_guard_execs_entrypoint_with_valid_secrets(tmp_path):
    result, marker = _run_guard(tmp_path)

    assert result.returncode == 0, result.stderr
    assert marker.exists()


@pytest.mark.parametrize("api_key", [None, ""])
def test_guard_rejects_missing_api_key(tmp_path, api_key):
    result, marker = _run_guard(tmp_path, api_key=api_key)

    assert result.returncode == 1
    assert "API_KEY is not set" in result.stderr
    assert not marker.exists()


@pytest.mark.parametrize(
    "api_key",
    [
        "short",
        "a" * 15,
        "a" * 129,
        "a" * 31 + ";",
        "a" * 31 + "}",
        "a" * 31 + "$",
        "a" * 31 + " ",
        "a" * 31 + "\n",
    ],
)
def test_guard_rejects_unsafe_or_out_of_range_api_keys(tmp_path, api_key):
    result, marker = _run_guard(tmp_path, api_key=api_key)

    assert result.returncode == 1
    assert not marker.exists()
    assert "FATAL" in result.stderr


def test_guard_rejects_missing_htpasswd_file(tmp_path):
    result, marker = _run_guard(tmp_path, htpasswd=None)

    assert result.returncode == 1
    assert "is missing" in result.stderr
    assert not marker.exists()


def test_guard_rejects_directory_at_htpasswd_path(tmp_path):
    result, marker = _run_guard(tmp_path, make_dir=True)

    assert result.returncode == 1
    assert "is a directory" in result.stderr
    assert not marker.exists()


def test_guard_rejects_empty_htpasswd_file(tmp_path):
    result, marker = _run_guard(tmp_path, htpasswd="")

    assert result.returncode == 1
    assert "is empty" in result.stderr
    assert not marker.exists()


def test_guard_rejects_htpasswd_without_a_user_hash_entry(tmp_path):
    result, marker = _run_guard(tmp_path, htpasswd="not-a-valid-entry\n")

    assert result.returncode == 1
    assert "user:hash" in result.stderr
    assert not marker.exists()
