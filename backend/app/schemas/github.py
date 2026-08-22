from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class RepositorySummary(BaseModel):
    name: str
    full_name: str
    owner: str
    description: str | None = None
    private: bool
    default_branch: str
    language: str | None = None
    stars: int = Field(default=0, alias="stargazers_count")
    forks: int = Field(default=0, alias="forks_count")
    open_issues: int = Field(default=0, alias="open_issues_count")
    html_url: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"populate_by_name": True}


class CommitSummary(BaseModel):
    sha: str
    short_sha: str
    message: str
    author: str | None = None
    author_email: str | None = None
    committed_at: datetime | None = None
    url: str | None = None

    @field_validator("short_sha", mode="before")
    @classmethod
    def set_short_sha(cls, value, info):
        if value is not None:
            return value
        data = info.data
        sha = data.get("sha") if isinstance(data, dict) else None
        return sha[:7] if sha else None


class PullRequestSummary(BaseModel):
    number: int
    title: str
    state: str
    author: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    merged_at: datetime | None = None
    url: str | None = None


class IssueSummary(BaseModel):
    number: int
    title: str
    state: str
    author: str | None = None
    labels: list[str] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None
    url: str | None = None


class RepositoryContent(BaseModel):
    name: str
    path: str
    type: str
    size: int | None = None
    url: str | None = None
