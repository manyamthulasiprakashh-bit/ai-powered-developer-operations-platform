from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  # register models on Base.metadata
from app.core.config import get_settings
from app.db.base import Base

TEST_API_KEY = "test-api-key"


@pytest.fixture(autouse=True)
def configured_api_key(monkeypatch):
    """Configure a deterministic API key and isolate rate-limit state per test."""
    from app.main import app

    monkeypatch.setenv("API_KEY", TEST_API_KEY)
    get_settings.cache_clear()
    app.state.rate_limiter.reset()
    app.state.analysis_rate_limiter.reset()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    return {"X-API-Key": TEST_API_KEY}


@pytest.fixture()
def db_engine():
    """Isolated in-memory SQLite engine; no live database server is required."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    testing_session = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    session = testing_session()
    try:
        yield session
    finally:
        session.close()
