from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./signal.db"
    musicbrainz_base_url: str = "https://musicbrainz.org/ws/2"
    musicbrainz_contact: str = "local-development@example.invalid"
    musicbrainz_user_agent: str = "Signal/0.1.0 (local-development@example.invalid)"
    musicbrainz_timeout_seconds: float = Field(default=10.0, gt=0)
    openai_api_key: str | None = None
    openai_model: str = "gpt-5-mini"
    log_level: str = "INFO"
    cors_origins: tuple[str, ...] = ("http://localhost:3000",)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.startswith("["):
            return tuple(origin.strip() for origin in value.split(",") if origin.strip())
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
