import logging
import re
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.routes.analyses import router as analyses_router
from app.api.routes.documents import router as documents_router
from app.api.routes.github import get_github_service, router as github_router
from app.core.config import get_settings
from app.core.exceptions import (
    AuthenticationConfigurationError,
    AuthenticationError,
    DocumentNotFoundError,
    DocumentNotDecidableError,
    DocumentNotExtractableError,
    DocumentTooLargeError,
    ExtractionOutputError,
    ExtractionProviderError,
    ExtractionTimeoutError,
    GitHubAuthError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubServiceError,
    GitHubTimeoutError,
    InvalidDocumentError,
    UnsupportedDocumentError,
)
from app.core.logging import configure_logging
from app.core.metrics import metrics
from app.core.request_limits import DocumentBodyLimitMiddleware
from app.core.security import (
    InMemoryRateLimiter,
    categorize_request,
    redact_sensitive,
    resolve_client_identity,
)
from app.db.session import get_db

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

# Registered first so it is the innermost user middleware: it still wraps the
# router (and therefore runs before multipart parsing and API-key resolution),
# while CORS/security/logging middleware wrap its responses.
app.add_middleware(DocumentBodyLimitMiddleware)

app.include_router(github_router)
app.include_router(analyses_router)
app.include_router(documents_router)

cors_origins = settings.cors_allowed_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"https://.*\.loca\.lt" if settings.app_env != "production" else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.state.rate_limiter = InMemoryRateLimiter(
    max_requests=settings.rate_limit_requests,
    window_seconds=settings.rate_limit_window_seconds,
)
app.state.analysis_rate_limiter = InMemoryRateLimiter(
    max_requests=settings.rate_limit_analysis_requests,
    window_seconds=settings.rate_limit_window_seconds,
)
app.state.trusted_proxy_ips = settings.trusted_proxy_ips

ANALYSIS_ROUTE = "/api/github/repositories/{owner}/{repo}/analysis"

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
    exempt_paths = {"/api/health", "/api/ready", "/health", "/ready", "/metrics"}
    if request.method != "OPTIONS" and request.url.path not in exempt_paths:
        peer_host = request.client.host if request.client else None
        client_key = resolve_client_identity(
            peer_host,
            request.headers.get("x-forwarded-for"),
            app.state.trusted_proxy_ips,
        )
        route_category = categorize_request(request.method, request.url.path)
        bucket = f"{client_key}:{request.method}:{route_category}"
        if request.method == "POST" and route_category == ANALYSIS_ROUTE:
            limiter = app.state.analysis_rate_limiter
        else:
            limiter = app.state.rate_limiter
        allowed, retry_after = limiter.allow(bucket)
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
    logger.info("request_started", extra={"method": request.method, "path": request.url.path, "request_id": request_id})
    metrics.increment("http_requests_total")
    try:
        response = await call_next(request)
    except Exception:
        metrics.increment("http_errors_total")
        logger.exception("request_failed", extra={"method": request.method, "path": request.url.path, "request_id": request_id})
        raise
    process_time = time.perf_counter() - start_time
    if response.status_code >= 400:
        metrics.increment("http_errors_total")
    metrics.observe_duration("http_request_duration_seconds", process_time)
    logger.info("request_completed", extra={"method": request.method, "path": request.url.path, "status": response.status_code, "duration_seconds": round(process_time, 6), "request_id": request_id})
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


@app.exception_handler(AuthenticationError)
async def authentication_exception_handler(request: Request, exc: AuthenticationError):
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={
            "detail": "Unauthorized.",
            "error": "unauthorized",
            "message": "Unauthorized.",
            "retryable": False,
        },
        headers={"WWW-Authenticate": "ApiKey"},
    )


@app.exception_handler(AuthenticationConfigurationError)
async def authentication_configuration_exception_handler(
    request: Request, exc: AuthenticationConfigurationError
):
    logger.error("authentication_not_configured")
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "detail": "Authentication is not configured.",
            "error": "authentication_not_configured",
            "message": "Authentication is not configured.",
            "retryable": False,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.info("request_validation_failed", extra={"method": request.method, "path": request.url.path, "request_id": getattr(request.state, "request_id", None)})
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


@app.exception_handler(UnsupportedDocumentError)
async def unsupported_document_exception_handler(request: Request, exc: UnsupportedDocumentError):
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Unsupported document type.",
            "error": "unsupported_document",
            "message": "Unsupported document type.",
            "retryable": False,
        },
    )


@app.exception_handler(DocumentTooLargeError)
async def document_too_large_exception_handler(request: Request, exc: DocumentTooLargeError):
    return JSONResponse(
        status_code=413,
        content={
            "detail": "Document exceeds the maximum allowed size.",
            "error": "document_too_large",
            "message": "Document exceeds the maximum allowed size.",
            "retryable": False,
        },
    )


@app.exception_handler(InvalidDocumentError)
async def invalid_document_exception_handler(request: Request, exc: InvalidDocumentError):
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Document is empty or is not valid UTF-8 text.",
            "error": "invalid_document",
            "message": "Document is empty or is not valid UTF-8 text.",
            "retryable": False,
        },
    )


@app.exception_handler(DocumentNotFoundError)
async def document_not_found_exception_handler(request: Request, exc: DocumentNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "detail": "Document not found.",
            "error": "document_not_found",
            "message": "Document not found.",
            "retryable": False,
        },
    )


@app.exception_handler(DocumentNotExtractableError)
async def document_not_extractable_exception_handler(
    request: Request, exc: DocumentNotExtractableError
):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "detail": "Document is not in an extractable state.",
            "error": "document_not_extractable",
            "message": "Document is not in an extractable state.",
            "retryable": False,
        },
    )


@app.exception_handler(DocumentNotDecidableError)
async def document_not_decidable_exception_handler(
    request: Request, exc: DocumentNotDecidableError
):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "detail": "Document is not in a decidable state.",
            "error": "document_not_decidable",
            "message": "Document is not in a decidable state.",
            "retryable": False,
        },
    )


@app.exception_handler(ExtractionTimeoutError)
async def extraction_timeout_exception_handler(request: Request, exc: ExtractionTimeoutError):
    logger.warning("extraction_timeout method=%s path=%s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        content={
            "detail": "Document extraction timed out.",
            "error": "extraction_timeout",
            "message": "Document extraction timed out.",
            "retryable": True,
        },
    )


@app.exception_handler(ExtractionOutputError)
async def extraction_output_exception_handler(request: Request, exc: ExtractionOutputError):
    logger.warning("extraction_output_invalid method=%s path=%s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={
            "detail": "Document extraction returned invalid output.",
            "error": "extraction_output_invalid",
            "message": "Document extraction returned invalid output.",
            "retryable": True,
        },
    )


@app.exception_handler(ExtractionProviderError)
async def extraction_provider_exception_handler(request: Request, exc: ExtractionProviderError):
    logger.warning("extraction_provider_failed method=%s path=%s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={
            "detail": "Document extraction service is unavailable.",
            "error": "extraction_provider_unavailable",
            "message": "Document extraction service is unavailable.",
            "retryable": True,
        },
    )


@app.exception_handler(Exception)
async def unexpected_exception_handler(request: Request, exc: Exception):
    logger.exception("unexpected_request_error method=%s path=%s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


@app.get("/metrics")
def metrics_endpoint():
    return metrics.snapshot()


@app.get("/api/health")
@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
    }


@app.get("/api/ready")
@app.get("/ready")
def readiness_check(db: Annotated[Session, Depends(get_db)]):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.warning("readiness_check_failed")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "service": settings.app_name,
                "checks": {"configuration": "ok", "database": "unavailable"},
            },
        )

    return {
        "status": "ready",
        "service": settings.app_name,
        "checks": {"configuration": "ok", "database": "ok"},
    }


@app.get("/")
def root():
    return {"message": "AI-Powered Developer Operations Platform API"}
