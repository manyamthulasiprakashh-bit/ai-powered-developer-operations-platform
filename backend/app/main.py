import logging
import re
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.github import get_github_service, router as github_router
from app.core.config import get_settings
from app.core.exceptions import (
    GitHubAuthError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubServiceError,
    GitHubTimeoutError,
)
from app.core.logging import configure_logging
from app.core.security import InMemoryRateLimiter, redact_sensitive

configure_logging()
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await get_github_service().aclose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="AI-Powered Developer Operations Platform",
    lifespan=lifespan,
)

app.include_router(github_router)

cors_origins = settings.cors_allowed_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"https://.*\.loca\.lt" if settings.app_env != "production" else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "bypass-tunnel-reminder"],
)
app.state.rate_limiter = InMemoryRateLimiter(
    max_requests=settings.rate_limit_requests,
    window_seconds=settings.rate_limit_window_seconds,
)

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")


def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'; base-uri 'self'"
    if settings.app_env == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    exempt_paths = {"/api/health", "/api/ready"}
    if request.method != "OPTIONS" and request.url.path not in exempt_paths:
        client_key = request.client.host if request.client else "unknown"
        allowed, retry_after = app.state.rate_limiter.allow(f"{client_key}:{request.url.path}")
        if not allowed:
            response = JSONResponse(status_code=429, content={"detail": "Too many requests."})
            response.headers["Retry-After"] = str(retry_after)
            return add_security_headers(response)

    response = await call_next(request)
    return add_security_headers(response)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    supplied_request_id = request.headers.get("X-Request-ID", "")
    request_id = supplied_request_id if REQUEST_ID_PATTERN.fullmatch(supplied_request_id) else str(uuid4())
    request.state.request_id = request_id
    start_time = time.perf_counter()
    logger.info("request_started method=%s path=%s request_id=%s", request.method, request.url.path, request_id)
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_failed method=%s path=%s request_id=%s", request.method, request.url.path, request_id)
        raise
    process_time = time.perf_counter() - start_time
    logger.info(
        "request method=%s path=%s status=%s duration=%.4fs request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        process_time,
        request_id,
    )
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    safe_details = {
        400: "Invalid request.",
        401: "GitHub authentication failed.",
        404: "Resource not found.",
        429: "Too many requests.",
        502: "GitHub service unavailable.",
        504: "GitHub request timed out.",
        503: "GitHub service temporarily unavailable.",
    }
    detail = safe_details.get(exc.status_code, exc.detail)
    if exc.status_code == 429 and exc.detail == "GitHub API rate limit exceeded. Please try again later.":
        detail = exc.detail
    error_name = {
        400: "invalid_request",
        401: "github_authentication_failed",
        404: "not_found",
        429: "rate_limited",
        502: "upstream_unavailable",
        504: "upstream_timeout",
        503: "circuit_open",
    }.get(exc.status_code, "request_error")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail, "error": error_name, "message": detail, "retryable": exc.status_code in {429, 502, 503, 504}},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.info("request_validation_failed method=%s path=%s", request.method, request.url.path)
    return JSONResponse(status_code=422, content={"detail": "Invalid request parameters.", "error": "invalid_request", "message": "Invalid request parameters.", "retryable": False})


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
    logger.warning("github_request_failed method=%s path=%s error=%s", request.method, request.url.path, redact_sensitive(exc))
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
