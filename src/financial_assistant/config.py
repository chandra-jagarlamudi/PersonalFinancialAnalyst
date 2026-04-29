"""Application configuration loaded from environment variables.

Usage:
    from financial_assistant.config import settings
"""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Required ────────────────────────────────────────────────────────────
    database_url: str
    google_client_id: str
    google_client_secret: str
    allowed_user_email: str
    langsmith_api_key: str
    anthropic_api_key: str
    mcp_api_key: str

    # ── Optional ────────────────────────────────────────────────────────────
    session_expiry_days: int = 30
    anthropic_model: str = "claude-sonnet-4-6"
    langsmith_project: str = "financial-assistant"
    log_level: str = "INFO"
    disable_auth: bool = False

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"LOG_LEVEL must be one of {valid}, got {v!r}")
        return upper

    @field_validator(
        "database_url",
        "google_client_id",
        "google_client_secret",
        "allowed_user_email",
        "langsmith_api_key",
        "anthropic_api_key",
        "mcp_api_key",
    )
    @classmethod
    def reject_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v

    def __repr__(self) -> str:
        return (
            f"Settings(database_url=***, google_client_id={self.google_client_id!r}, "
            f"allowed_user_email={self.allowed_user_email!r}, "
            f"anthropic_model={self.anthropic_model!r}, log_level={self.log_level!r}, "
            f"disable_auth={self.disable_auth!r})"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
