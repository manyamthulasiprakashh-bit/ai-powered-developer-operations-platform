from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_db
from app.main import app
from app.models import Analysis
from app.services import analysis_history

METRICS = {
    "commit_count": 4,
    "open_issue_count": 2,
    "open_pull_request_count": 1,
    "root_content_count": 6,
    "has_readme": True,
    "has_ci_configuration": True,
}

FINDINGS = [
    {
        "title": "Large open issue backlog",
        "description": "The repository reports more than twenty open issues.",
        "severity": "MEDIUM",
        "category": "maintenance",
        "evidence": "open_issue_count=2",
    }
]


@pytest.fixture()
def client(db_session, auth_headers):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app, headers=auth_headers)
    finally:
        app.dependency_overrides.clear()


def _seed(db, owner, repository, analyzed_at, summary="Summary"):
    record = Analysis(
        owner=owner,
        repository=repository,
        analyzed_at=analyzed_at,
        summary=summary,
        metrics=METRICS,
        findings=FINDINGS,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _seed_ordered_history(db):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _seed(db, "alpha", "one", base)
    _seed(db, "beta", "two", base + timedelta(days=2))
    _seed(db, "alpha", "three", base + timedelta(days=2))
    _seed(db, "gamma", "one", base + timedelta(days=1))
    _seed(db, "beta", "two", base + timedelta(days=1))


def test_list_analyses_is_newest_first_with_stable_id_tie_breaker(client, db_session):
    _seed_ordered_history(db_session)

    first_page = client.get("/api/analyses?limit=2&offset=0")
    assert first_page.status_code == 200
    payload = first_page.json()
    assert payload["total"] == 5
    assert payload["limit"] == 2
    assert payload["offset"] == 0
    assert [item["id"] for item in payload["items"]] == [3, 2]

    second_page = client.get("/api/analyses?limit=2&offset=2").json()
    assert [item["id"] for item in second_page["items"]] == [5, 4]
    assert second_page["total"] == 5

    final_page = client.get("/api/analyses?limit=2&offset=4").json()
    assert [item["id"] for item in final_page["items"]] == [1]


def test_get_analysis_detail_returns_stored_payload(client, db_session):
    record = _seed(
        db_session,
        "microsoft",
        "vscode",
        datetime(2026, 2, 1, tzinfo=timezone.utc),
        summary="Analyzed vscode.",
    )

    response = client.get(f"/api/analyses/{record.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == record.id
    assert payload["owner"] == "microsoft"
    assert payload["repository"] == "vscode"
    assert payload["summary"] == "Analyzed vscode."
    assert payload["metrics"] == METRICS
    assert payload["findings"] == FINDINGS
    assert payload["created_at"]


def test_get_analysis_detail_returns_404_for_missing_record(client):
    response = client.get("/api/analyses/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Resource not found."
    assert response.json()["error"] == "not_found"


def test_statistics_are_empty_without_analyses(client):
    response = client.get("/api/statistics")

    assert response.status_code == 200
    assert response.json() == {
        "total_analyses": 0,
        "distinct_owners": 0,
        "distinct_repositories": 0,
        "analyses_last_7_days": 0,
        "analyses_last_30_days": 0,
        "latest_analyzed_at": None,
    }


def test_statistics_are_database_backed(client, db_session):
    now = datetime.now(timezone.utc)
    _seed(db_session, "alpha", "one", now - timedelta(days=1))
    _seed(db_session, "alpha", "two", now - timedelta(days=10))
    _seed(db_session, "beta", "one", now - timedelta(days=40))

    response = client.get("/api/statistics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_analyses"] == 3
    assert payload["distinct_owners"] == 2
    assert payload["distinct_repositories"] == 3
    assert payload["analyses_last_7_days"] == 1
    assert payload["analyses_last_30_days"] == 2
    assert payload["latest_analyzed_at"] is not None


@pytest.mark.parametrize(
    "query",
    ["limit=0", "limit=101", "offset=-1"],
)
def test_invalid_pagination_returns_safe_validation_error(client, query):
    response = client.get(f"/api/analyses?{query}")

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid request parameters."
    assert response.json()["error"] == "invalid_request"


def test_list_analyses_hides_database_errors(client, monkeypatch):
    def failing_query(*args, **kwargs):
        raise OperationalError(
            "SELECT * FROM analyses WHERE password=super-secret",
            {"password": "super-secret"},
            Exception("database unavailable"),
        )

    monkeypatch.setattr(analysis_history, "list_analyses", failing_query)

    response = client.get("/api/analyses")

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error."
    assert "super-secret" not in response.text
    assert "SELECT" not in response.text


def test_statistics_hides_database_errors(client, monkeypatch):
    def failing_query(*args, **kwargs):
        raise OperationalError(
            "SELECT password FROM analyses",
            {"password": "super-secret"},
            Exception("database unavailable"),
        )

    monkeypatch.setattr(analysis_history, "get_statistics", failing_query)

    response = client.get("/api/statistics")

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error."
    assert "super-secret" not in response.text
    assert "SELECT" not in response.text
