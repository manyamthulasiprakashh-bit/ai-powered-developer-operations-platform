from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.exceptions import (
    GitHubAuthError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubServiceError,
    GitHubTimeoutError,
)
from app.services.github_service import GitHubService

router = APIRouter(prefix="/api/github", tags=["GitHub"])


def get_github_service() -> GitHubService:
    return GitHubService()


@router.get(
    "/repositories/{owner}/{repo}",
    summary="Get repository metadata",
    description="Retrieve summary data for a GitHub repository.",
)
def get_repository(
    owner: str,
    repo: str,
    service: Annotated[GitHubService, Depends(get_github_service)],
):
    try:
        return service.get_repository(owner, repo).model_dump(mode="json")
    except GitHubNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except GitHubAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except GitHubRateLimitError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except GitHubTimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except GitHubServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get(
    "/repositories/{owner}/{repo}/commits",
    summary="Get repository commits",
    description="Retrieve recent commits with pagination support.",
)
def get_commits(
    owner: str,
    repo: str,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 30,
    service: Annotated[GitHubService, Depends(get_github_service)] = None,
):
    try:
        commits = service.get_commits(owner, repo, page=page, per_page=per_page)
        return [item.model_dump(mode="json") for item in commits]
    except GitHubNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except GitHubAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except GitHubRateLimitError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except GitHubTimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except GitHubServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get(
    "/repositories/{owner}/{repo}/pull-requests",
    summary="Get pull requests",
    description="Retrieve pull requests for the repository, filtered by state.",
)
def get_pull_requests(
    owner: str,
    repo: str,
    state: Literal["open", "closed", "all"] = "open",
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 30,
    service: Annotated[GitHubService, Depends(get_github_service)] = None,
):
    try:
        prs = service.get_pull_requests(owner, repo, state=state, page=page, per_page=per_page)
        return [item.model_dump(mode="json") for item in prs]
    except GitHubNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except GitHubAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except GitHubRateLimitError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except GitHubTimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except GitHubServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get(
    "/repositories/{owner}/{repo}/issues",
    summary="Get repository issues",
    description="Retrieve issues while excluding pull requests from the list.",
)
def get_issues(
    owner: str,
    repo: str,
    state: Literal["open", "closed", "all"] = "open",
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 30,
    service: Annotated[GitHubService, Depends(get_github_service)] = None,
):
    try:
        issues = service.get_issues(owner, repo, state=state, page=page, per_page=per_page)
        return [item.model_dump(mode="json") for item in issues]
    except GitHubNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except GitHubAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except GitHubRateLimitError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except GitHubTimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except GitHubServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get(
    "/repositories/{owner}/{repo}/contents",
    summary="Get repository contents",
    description="List contents for the repository root or a specific path with a safe page limit.",
)
def get_contents(
    owner: str,
    repo: str,
    path: str = "",
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=50)] = 30,
    service: Annotated[GitHubService, Depends(get_github_service)] = None,
):
    try:
        contents = service.get_contents(owner, repo, path=path, page=page, per_page=per_page)
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
    except GitHubServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
