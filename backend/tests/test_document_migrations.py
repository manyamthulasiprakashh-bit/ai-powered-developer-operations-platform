from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

BACKEND_DIR = Path(__file__).resolve().parents[1]
VERSIONS_DIR = BACKEND_DIR / "migrations" / "versions"
DOCUMENT_TABLES = {"documents", "document_extractions", "document_decisions", "audit_events"}


def _load_migration(filename: str):
    spec = importlib.util.spec_from_file_location(f"migration_{filename}", VERSIONS_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def alembic_env(tmp_path, monkeypatch):
    """Point Alembic at an isolated SQLite file via application settings.

    A bare ``Config`` (no ``alembic.ini``) is used so ``migrations/env.py`` skips
    ``fileConfig`` and does not reconfigure global logging during tests.
    """
    database_url = f"sqlite:///{tmp_path / 'migration_test.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    from app.core.config import get_settings

    get_settings.cache_clear()
    config = Config()
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    try:
        yield config, database_url
    finally:
        get_settings.cache_clear()


def test_migration_module_links_to_previous_revision():
    module = _load_migration("0002_create_documents.py")

    assert module.revision == "0002_create_documents"
    assert module.down_revision == "0001_create_analyses"
    assert callable(module.upgrade)
    assert callable(module.downgrade)


def test_upgrade_creates_document_tables_and_downgrade_removes_only_them(alembic_env):
    config, database_url = alembic_env
    engine = create_engine(database_url)
    try:
        command.upgrade(config, "head")
        tables_after_upgrade = set(inspect(engine).get_table_names())
        assert {"analyses", *DOCUMENT_TABLES} <= tables_after_upgrade

        command.downgrade(config, "0001_create_analyses")
        tables_after_downgrade = set(inspect(engine).get_table_names())
        assert "analyses" in tables_after_downgrade
        assert DOCUMENT_TABLES.isdisjoint(tables_after_downgrade)

        command.upgrade(config, "head")
        assert {"analyses", *DOCUMENT_TABLES} <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_downgrade_preserves_existing_analysis_rows(alembic_env):
    config, database_url = alembic_env
    engine = create_engine(database_url)
    try:
        command.upgrade(config, "0001_create_analyses")
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO analyses (owner, repository, analyzed_at, summary, metrics, findings) "
                    "VALUES (:owner, :repository, :analyzed_at, :summary, :metrics, :findings)"
                ),
                {
                    "owner": "acme",
                    "repository": "repo",
                    "analyzed_at": "2026-01-01 00:00:00",
                    "summary": "s",
                    "metrics": "{}",
                    "findings": "[]",
                },
            )

        command.upgrade(config, "head")
        command.downgrade(config, "0001_create_analyses")

        with engine.connect() as connection:
            remaining = connection.execute(sa.text("SELECT COUNT(*) FROM analyses")).scalar_one()
        assert remaining == 1
    finally:
        engine.dispose()
