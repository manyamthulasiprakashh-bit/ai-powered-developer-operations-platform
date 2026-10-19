from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AnalysisFinding(BaseModel):
    title: str
    description: str
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
    category: str
    evidence: str


class AnalysisMetrics(BaseModel):
    commit_count: int = Field(ge=0)
    open_issue_count: int = Field(ge=0)
    open_pull_request_count: int = Field(ge=0)
    root_content_count: int = Field(ge=0)
    has_readme: bool
    has_ci_configuration: bool


class RepositoryAnalysisResponse(BaseModel):
    owner: str
    repository: str
    analyzed_at: datetime
    summary: str
    metrics: AnalysisMetrics
    findings: list[AnalysisFinding] = Field(default_factory=list)


class AnalysisListItem(BaseModel):
    """Summary fields for a persisted analysis in history listings."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="Persisted analysis record identifier.")
    owner: str = Field(description="GitHub repository owner.")
    repository: str = Field(description="GitHub repository name.")
    analyzed_at: datetime = Field(description="Timestamp recorded when the analysis ran.")
    summary: str = Field(description="Human-readable analysis summary.")
    created_at: datetime = Field(description="Timestamp when the record was stored.")


class AnalysisDetail(AnalysisListItem):
    """Full persisted analysis, including metrics and findings."""

    metrics: AnalysisMetrics = Field(description="Deterministic metrics captured at analysis time.")
    findings: list[AnalysisFinding] = Field(
        default_factory=list,
        description="Findings produced by the deterministic analysis rules.",
    )


class AnalysisListResponse(BaseModel):
    """Bounded, newest-first page of persisted analyses."""

    items: list[AnalysisListItem] = Field(description="Analyses for the requested page.")
    total: int = Field(ge=0, description="Total number of persisted analyses.")
    limit: int = Field(ge=1, description="Maximum number of records requested.")
    offset: int = Field(ge=0, description="Number of records skipped.")


class StatisticsResponse(BaseModel):
    """Database-backed aggregate values derived from stored analyses."""

    total_analyses: int = Field(ge=0, description="Total persisted analyses.")
    distinct_owners: int = Field(ge=0, description="Number of distinct repository owners.")
    distinct_repositories: int = Field(ge=0, description="Number of distinct owner/repository pairs.")
    analyses_last_7_days: int = Field(ge=0, description="Analyses whose analyzed_at is within the last 7 days.")
    analyses_last_30_days: int = Field(ge=0, description="Analyses whose analyzed_at is within the last 30 days.")
    latest_analyzed_at: datetime | None = Field(
        default=None,
        description="Most recent analyzed_at value, or null when no analyses exist.",
    )
