from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models import Analysis


def list_analyses(db: Session, limit: int, offset: int) -> tuple[list[Analysis], int]:
    """Return one page of analyses newest-first with a deterministic tie-breaker."""
    total = db.execute(select(func.count(Analysis.id))).scalar_one()
    records = (
        db.execute(
            select(Analysis)
            .order_by(Analysis.analyzed_at.desc(), Analysis.id.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return list(records), total


def get_analysis(db: Session, analysis_id: int) -> Analysis | None:
    return db.get(Analysis, analysis_id)


def get_statistics(db: Session, now: datetime | None = None) -> dict[str, Any]:
    """Compute aggregate values directly from the analyses table."""
    current_time = now or datetime.now(timezone.utc)

    total_analyses, distinct_owners, latest_analyzed_at = db.execute(
        select(
            func.count(Analysis.id),
            func.count(distinct(Analysis.owner)),
            func.max(Analysis.analyzed_at),
        )
    ).one()

    distinct_repositories = db.execute(
        select(func.count()).select_from(
            select(Analysis.owner, Analysis.repository).distinct().subquery()
        )
    ).scalar_one()

    analyses_last_7_days = db.execute(
        select(func.count(Analysis.id)).where(
            Analysis.analyzed_at >= current_time - timedelta(days=7)
        )
    ).scalar_one()

    analyses_last_30_days = db.execute(
        select(func.count(Analysis.id)).where(
            Analysis.analyzed_at >= current_time - timedelta(days=30)
        )
    ).scalar_one()

    return {
        "total_analyses": total_analyses,
        "distinct_owners": distinct_owners,
        "distinct_repositories": distinct_repositories,
        "analyses_last_7_days": analyses_last_7_days,
        "analyses_last_30_days": analyses_last_30_days,
        "latest_analyzed_at": latest_analyzed_at,
    }
