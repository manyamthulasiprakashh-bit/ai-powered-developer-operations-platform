from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.core.exceptions import (
    GitHubAuthError,
    GitHubCircuitOpenError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubServiceError,
    GitHubTimeoutError,
)
from app.core.config import get_settings
from app.schemas.analysis import RepositoryAnalysisResponse
from app.services.analysis_service import RepositoryAnalysisService
from app.services.github_service import GitHubService

router = APIRouter(prefix="/api/github", tags=["GitHub"])
settings = get_settings()

RepositoryPart = Annotated[str, Path(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")]
ContentPath = Annotated[str, Query(max_length=512)]


@lru_cache
def get_github_service() -> GitHubService:
    return GitHubService()


def get_analysis_service(
    service: Annotated[GitHubService, Depends(get_github_service)],
) -> RepositoryAnalysisService:
    return RepositoryAnalysisService(service)


@router.get(
    "/repositories/{owner}/{repo}",
    summary="Get repository metadata",
    description="Retrieve summary data for a GitHub repository.",
)
async def get_repository(
    owner: RepositoryPart,
    repo: RepositoryPart,
    service: Annotated[GitHubService, Depends(get_github_service)],
):
    try:
        return (await service.get_repository_async(owner, repo)).model_dump(mode="json")
    except GitHubNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except GitHubAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except GitHubRateLimitError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except GitHubTimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except GitHubCircuitOpenError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except GitHubServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post(
    "/repositories/{owner}/{repo}/analysis",
    response_model=RepositoryAnalysisResponse,
    summary="Analyze a repository",
    description="Run deterministic V1 analysis using repository data retrieved from GitHub.",
)
async def analyze_repository(
    owner: RepositoryPart,
    repo: RepositoryPart,
    service: Annotated[RepositoryAnalysisService, Depends(get_analysis_service)],
):
    try:
        return await service.analyze(owner, repo)
    except GitHubNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except GitHubAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except GitHubRateLimitError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except GitHubTimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except GitHubCircuitOpenError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except GitHubServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get(
    "/repositories/{owner}/{repo}/commits",
    summary="Get repository commits",
    description="Retrieve recent commits with pagination support.",
)
async def get_commits(
    owner: RepositoryPart,
    repo: RepositoryPart,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=settings.github_max_per_page)] = 30,
    service: Annotated[GitHubService, Depends(get_github_service)] = None,
):
    try:
        commits = await service.get_commits_async(owner, repo, page=page, per_page=per_page)
        return [item.model_dump(mode="json") for item in commits]
    except GitHubNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except GitHubAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except GitHubRateLimitError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except GitHubTimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except GitHubCircuitOpenError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except GitHubServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get(
    "/repositories/{owner}/{repo}/pull-requests",
    summary="Get pull requests",
    description="Retrieve pull requests for the repository, filtered by state.",
)
async def get_pull_requests(
    owner: RepositoryPart,
    repo: RepositoryPart,
    state: Literal["open", "closed", "all"] = "open",
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=settings.github_max_per_page)] = 30,
    service: Annotated[GitHubService, Depends(get_github_service)] = None,
):
    try:
        prs = await service.get_pull_requests_async(owner, repo, state=state, page=page, per_page=per_page)
        return [item.model_dump(mode="json") for item in prs]
    except GitHubNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except GitHubAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except GitHubRateLimitError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except GitHubTimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except GitHubCircuitOpenError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except GitHubServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get(
    "/repositories/{owner}/{repo}/issues",
    summary="Get repository issues",
    description="Retrieve issues while excluding pull requests from the list.",
)
async def get_issues(
    owner: RepositoryPart,
    repo: RepositoryPart,
    state: Literal["open", "closed", "all"] = "open",
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=settings.github_max_per_page)] = 30,
    service: Annotated[GitHubService, Depends(get_github_service)] = None,
):
    try:
        issues = await service.get_issues_async(owner, repo, state=state, page=page, per_page=per_page)
        return [item.model_dump(mode="json") for item in issues]
    except GitHubNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except GitHubAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except GitHubRateLimitError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except GitHubTimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except GitHubCircuitOpenError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except GitHubServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get(
    "/repositories/{owner}/{repo}/contents",
    summary="Get repository contents",
    description="List contents for the repository root or a specific path with a safe page limit.",
)
async def get_contents(
    owner: RepositoryPart,
    repo: RepositoryPart,
    path: ContentPath = "",
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=50)] = 30,
    service: Annotated[GitHubService, Depends(get_github_service)] = None,
):
    if ".." in path.split("/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid repository path.")
    try:
        contents = await service.get_contents_async(owner, repo, path=path, page=page, per_page=per_page)
        if isinstance(contents, list):
            return [item.model_dump(mode="json") for item in contents]
        return contents.model_dump(mode="json")
    except GitHubNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except GitHubAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except GitHubRateLimitError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except GitHubTimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except GitHubCircuitOpenError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except GitHubServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
