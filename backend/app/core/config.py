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
    rate_limit_window_seconds: int = Field(default=60, ge=1)

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
