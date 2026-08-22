from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="ai-devops-platform")
    app_env: Literal["development", "production", "test"] = Field(default="development")
    app_debug: bool = Field(default=True)
    backend_host: str = Field(default="0.0.0.0")
    backend_port: int = Field(default=8000)
    database_url: str = Field(default="postgresql://postgres:postgres@db:5432/devops_platform")
    github_api_url: str = Field(default="https://api.github.com")
    github_token: str | None = Field(default=None)
    openai_api_key: str | None = Field(default=None)
    openai_model: str = Field(default="gpt-4o-mini")

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
