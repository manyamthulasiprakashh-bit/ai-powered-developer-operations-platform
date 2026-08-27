from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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