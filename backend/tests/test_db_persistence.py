from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import inspect, select

from app.db.session import normalize_database_url
from app.models import Analysis

METRICS = {
    "commit_count": 1,
    "open_issue_count": 1,
    "open_pull_request_count": 1,
    "root_content_count": 1,
    "has_readme": True,
    "has_ci_configuration": False,
}

FINDINGS = [
    {
        "title": "CI configuration not detected",
        "description": "No common CI configuration was present in the analyzed root contents.",
        "severity": "INFO",
        "category": "automation",
        "evidence": "has_ci_configuration=false",
    }
]

EXPECTED_COLUMNS = {
    "id",
    "owner",
    "repository",
    "analyzed_at",
    "summary",
    "metrics",
    "findings",
    "created_at",
}


def test_normalize_database_url_uses_psycopg_v3_driver():
    assert (
        normalize_database_url("postgresql://user:pass@db:5432/platform")
        == "postgresql+psycopg://user:pass@db:5432/platform"
    )
    assert (
        normalize_database_url("postgresql+psycopg2://user@db/platform")
        == "postgresql+psycopg://user@db/platform"
    )
    assert (
        normalize_database_url("postgresql+psycopg://user@db/platform")
        == "postgresql+psycopg://user@db/platform"
    )
    assert normalize_database_url("sqlite://") == "sqlite://"


def test_session_module_imports_without_a_running_database():
    # Importing the module already succeeded at collection time; the engine must be
    # configured for the psycopg v3 dialect without opening a connection.
    import app.db.session as session_module

    assert session_module.engine.dialect.name == "postgresql"
    assert session_module.engine.dialect.driver == "psycopg"


def test_analyses_table_is_created(db_engine):
    inspector = inspect(db_engine)

    assert "analyses" in inspector.get_table_names()
    assert {column["name"] for column in inspector.get_columns("analyses")} == EXPECTED_COLUMNS

    index_names = {index["name"] for index in inspector.get_indexes("analyses")}
    assert {"ix_analyses_owner", "ix_analyses_repository"} <= index_names


def test_analysis_round_trip_preserves_payloads(db_session):
    analyzed_at = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    record = Analysis(
        owner="microsoft",
        repository="vscode",
        analyzed_at=analyzed_at,
        summary="Repository analysis completed with highest finding severity: INFO.",
        metrics=METRICS,
        findings=FINDINGS,
    )

    db_session.add(record)
    db_session.commit()

    stored = db_session.execute(select(Analysis)).scalar_one()
    assert stored.id is not None
    assert stored.owner == "microsoft"
    assert stored.repository == "vscode"
    assert stored.summary.startswith("Repository analysis completed")
    assert stored.metrics == METRICS
    assert stored.findings == FINDINGS
    assert stored.created_at is not None
