import logging
import time

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.github import router as github_router
from app.core.config import get_settings
from app.core.exceptions import (
    GitHubAuthError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubServiceError,
    GitHubTimeoutError,
)
from app.core.logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="AI-Powered Developer Operations Platform",
)

app.include_router(github_router)

cors_origins = settings.cors_allowed_origins or ["http://localhost:5173", "http://127.0.0.1:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"https://.*\.loca\.lt",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "bypass-tunnel-reminder"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start_time = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_failed method=%s path=%s", request.method, request.url.path)
        raise
    process_time = time.perf_counter() - start_time
    logger.info(
        "request method=%s path=%s status=%s duration=%.4fs",
        request.method,
        request.url.path,
        response.status_code,
        process_time,
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.info("request_validation_failed method=%s path=%s", request.method, request.url.path)
    return JSONResponse(status_code=422, content={"detail": "Invalid request parameters."})


@app.exception_handler(GitHubAuthError)
async def github_auth_exception_handler(request: Request, exc: GitHubAuthError):
    return JSONResponse(status_code=401, content={"detail": str(exc)})


@app.exception_handler(GitHubNotFoundError)
async def github_not_found_exception_handler(request: Request, exc: GitHubNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(GitHubRateLimitError)
async def github_rate_limit_exception_handler(request: Request, exc: GitHubRateLimitError):
    return JSONResponse(status_code=429, content={"detail": str(exc)})


@app.exception_handler(GitHubTimeoutError)
async def github_timeout_exception_handler(request: Request, exc: GitHubTimeoutError):
    return JSONResponse(status_code=504, content={"detail": str(exc)})


@app.exception_handler(GitHubServiceError)
async def github_service_exception_handler(request: Request, exc: GitHubServiceError):
    logger.warning("github_request_failed method=%s path=%s error=%s", request.method, request.url.path, exc)
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unexpected_exception_handler(request: Request, exc: Exception):
    logger.exception("unexpected_request_error method=%s path=%s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
    }


@app.get("/api/ready")
def readiness_check():
    return {
        "status": "ready",
        "service": settings.app_name,
        "checks": {"configuration": "ok"},
    }


@app.get("/")
def root():
    return {"message": "AI-Powered Developer Operations Platform API"}
