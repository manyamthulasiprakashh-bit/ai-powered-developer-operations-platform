from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base

settings = get_settings()

_PSYCOPG_DRIVER = "postgresql+psycopg"
_LEGACY_POSTGRES_DRIVERS = {"postgresql", "postgresql+psycopg2"}


def normalize_database_url(database_url: str) -> str:
    """Return a SQLAlchemy URL that uses the installed psycopg v3 driver.

    Legacy ``postgresql://`` (and ``postgresql+psycopg2://``) URLs are rewritten so
    they resolve to ``postgresql+psycopg://`` instead of the uninstalled psycopg2.
    Non-PostgreSQL URLs are returned unchanged.
    """
    url = make_url(database_url)
    if url.drivername in _LEGACY_POSTGRES_DRIVERS:
        url = url.set(drivername=_PSYCOPG_DRIVER)
    return url.render_as_string(hide_password=False)


# Engine creation is lazy: no connection is opened until a session executes a query.
engine = create_engine(normalize_database_url(settings.database_url), pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


__all__ = ["Base", "SessionLocal", "engine", "get_db", "normalize_database_url"]
