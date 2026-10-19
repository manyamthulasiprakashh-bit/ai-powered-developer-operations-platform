import os
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.security import validate_cors_origins


class Settings(BaseSettings):
    app_name: str = Field(default="ai-devops-platform")
    app_env: Literal["development", "production", "test"] = Field(default="development")
    app_debug: bool = Field(default=True)
    backend_host: str = Field(default="0.0.0.0")
    backend_port: int = Field(default=8000, validation_alias=AliasChoices("BACKEND_PORT", "PORT"))
    database_url: str = Field(default="postgresql://postgres@db:5432/devops_platform")
    github_api_url: str = Field(default="https://api.github.com")
    github_token: str | None = Field(default=None)
    openai_api_key: str | None = Field(default=None)
    openai_model: str = Field(default="gpt-4o-mini")
    cors_allowed_origins: str | list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"],
        validation_alias=AliasChoices("CORS_ALLOWED_ORIGINS", "CORS_ORIGINS"),
    )
    rate_limit_requests: int = Field(default=60, ge=1)
    rate_limit_analysis_requests: int = Field(default=10, ge=1)
    rate_limit_window_seconds: int = Field(default=60, ge=1)
    trusted_proxy_ips: str | list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("TRUSTED_PROXY_IPS", "TRUSTED_PROXIES"),
    )
    api_key: str | None = Field(default=None)
    document_max_size_bytes: int = Field(default=1_048_576, ge=1, le=16_777_216)
    document_max_text_chars: int = Field(default=20_000, ge=1, le=200_000)
    document_preview_chars: int = Field(default=500, ge=1, le=2_000)
    document_multipart_overhead_bytes: int = Field(default=65_536, ge=0, le=1_048_576)
    document_allowed_content_types: str | list[str] = Field(
        default_factory=lambda: ["text/plain", "text/markdown"]
    )
    document_allowed_extensions: str | list[str] = Field(
        default_factory=lambda: [".txt", ".md"]
    )
    github_connect_timeout: float = Field(default=5.0, gt=0)
    github_read_timeout: float = Field(default=15.0, gt=0)
    github_max_connections: int = Field(default=100, ge=1)
    github_max_keepalive_connections: int = Field(default=20, ge=1)
    github_max_per_page: int = Field(default=100, ge=1, le=100)
    cache_enabled: bool = True
    cache_ttl_seconds: float = Field(default=60.0, ge=0)
    cache_max_entries: int = Field(default=500, ge=1)
    github_max_retries: int = Field(default=2, ge=0, le=5)
    github_retry_base_delay_seconds: float = Field(default=0.25, ge=0, le=10)
    github_retry_max_delay_seconds: float = Field(default=2.0, ge=0, le=30)
    circuit_breaker_enabled: bool = True
    circuit_breaker_failure_threshold: int = Field(default=5, ge=1)
    circuit_breaker_reset_timeout_seconds: float = Field(default=30.0, gt=0)
    circuit_breaker_half_open_max_calls: int = Field(default=1, ge=1)

    @field_validator("backend_port", mode="before")
    @classmethod
    def validate_backend_port(cls, value):
        if value in (None, ""):
            return int(os.getenv("PORT", "8000"))
        return int(value)

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def validate_cors_allowed_origins(cls, value):
        if value in (None, ""):
            return ["http://localhost:5173", "http://127.0.0.1:5173"]
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("cors_allowed_origins", mode="after")
    @classmethod
    def validate_cors_policy(cls, value, info):
        origins = [value] if isinstance(value, str) else value
        environment = info.data.get("app_env", "development")
        return validate_cors_origins(origins, environment)

    @field_validator("trusted_proxy_ips", mode="before")
    @classmethod
    def validate_trusted_proxy_ips(cls, value):
        if value in (None, ""):
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("document_allowed_content_types", mode="before")
    @classmethod
    def validate_document_content_types(cls, value):
        if value in (None, ""):
            return ["text/plain", "text/markdown"]
        items = value.split(",") if isinstance(value, str) else value
        return [str(item).split(";")[0].strip().lower() for item in items if str(item).strip()]

    @field_validator("document_allowed_extensions", mode="before")
    @classmethod
    def validate_document_extensions(cls, value):
        if value in (None, ""):
            return [".txt", ".md"]
        items = value.split(",") if isinstance(value, str) else value
        normalized = []
        for item in items:
            extension = str(item).strip().lower()
            if not extension:
                continue
            normalized.append(extension if extension.startswith(".") else f".{extension}")
        return normalized

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def document_max_request_bytes(self) -> int:
        """Hard cap for the whole multipart upload request (file + framing)."""
        return self.document_max_size_bytes + self.document_multipart_overhead_bytes


@lru_cache
def get_settings() -> Settings:
    return Settings()
