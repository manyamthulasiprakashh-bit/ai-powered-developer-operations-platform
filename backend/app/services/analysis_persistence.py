from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Analysis
from app.schemas.analysis import RepositoryAnalysisResponse


def persist_analysis(db: Session, analysis: RepositoryAnalysisResponse) -> Analysis:
    """Persist a completed repository analysis.

    The record is built entirely from the already-computed response and the
    transaction is committed only after a successful analysis result exists. On
    any database failure the transaction is rolled back before the error is
    re-raised so callers can respond without leaking internal details.
    """
    record = Analysis(
        owner=analysis.owner,
        repository=analysis.repository,
        analyzed_at=analysis.analyzed_at,
        summary=analysis.summary,
        metrics=analysis.metrics.model_dump(mode="json"),
        findings=[finding.model_dump(mode="json") for finding in analysis.findings],
    )
    try:
        db.add(record)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return record
