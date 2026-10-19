from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import require_api_key
from app.db.session import get_db
from app.schemas.analysis import (
    AnalysisDetail,
    AnalysisListItem,
    AnalysisListResponse,
    StatisticsResponse,
)
from app.services import analysis_history

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Analyses"], dependencies=[Depends(require_api_key)])

SAFE_DB_ERROR_DETAIL = "Internal server error."


def _raise_safe_db_error(operation: str, exc: SQLAlchemyError) -> None:
    logger.error("%s_failed error=%s", operation, type(exc).__name__)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=SAFE_DB_ERROR_DETAIL,
    ) from exc


@router.get(
    "/analyses",
    response_model=AnalysisListResponse,
    summary="List persisted analyses",
    description="Return persisted repository analyses newest first with bounded pagination.",
)
async def list_analyses(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    try:
        records, total = await run_in_threadpool(
            analysis_history.list_analyses, db, limit, offset
        )
    except SQLAlchemyError as exc:
        _raise_safe_db_error("analysis_list", exc)

    return AnalysisListResponse(
        items=[AnalysisListItem.model_validate(record) for record in records],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/analyses/{analysis_id}",
    response_model=AnalysisDetail,
    summary="Get a persisted analysis",
    description="Return one stored analysis by identifier, or 404 when it does not exist.",
)
async def get_analysis(
    analysis_id: Annotated[int, Path(ge=1)],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        record = await run_in_threadpool(
            analysis_history.get_analysis, db, analysis_id
        )
    except SQLAlchemyError as exc:
        _raise_safe_db_error("analysis_detail", exc)

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis not found.",
        )

    return AnalysisDetail.model_validate(record)


@router.get(
    "/statistics",
    response_model=StatisticsResponse,
    summary="Get analysis statistics",
    description="Return database-backed aggregate values computed from stored analyses.",
)
async def get_statistics(db: Annotated[Session, Depends(get_db)]):
    try:
        values = await run_in_threadpool(analysis_history.get_statistics, db)
    except SQLAlchemyError as exc:
        _raise_safe_db_error("statistics", exc)

    return StatisticsResponse(**values)
