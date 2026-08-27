from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables.

    All variables are prefixed with ``CARE_`` (e.g. ``CARE_LLM_MODE``).
    Sensible defaults allow the full stack to run in ``mock`` mode without
    any external services.
    """

    model_config = SettingsConfigDict(
        env_prefix="CARE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_mode: Literal["mock", "real"] = "mock"
    database_url: str = "postgresql://care:care@localhost:5432/care"
    qc_risk_threshold: float = Field(default=0.75, gt=0.0, le=1.0)
    api_port: int = 8000


@lru_cache
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""
    return Settings()
