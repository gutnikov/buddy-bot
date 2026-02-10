"""Configuration module — loads and validates environment variables."""

import logging
import os
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator


class Settings(BaseModel):
    # Required
    anthropic_api_key: str
    telegram_token: str
    telegram_allowed_chat_ids: list[int]
    openai_api_key: str
    voyage_api_key: str

    # Optional with defaults
    model: str = "claude-sonnet-4-5-20250929"
    max_tokens: int = 4096
    temperature: float = 0.7
    history_turns: int = 20
    history_max_chars: int = 500
    history_db: str = "/data/history.db"
    debounce_delay: int = 5
    user_timezone: str = "UTC"
    graphiti_url: str = "http://graphiti-mcp:8000"
    tavily_api_key: str = ""
    perplexity_api_key: str = ""
    google_credentials_path: str = "/app/credentials/google_credentials.json"
    telegram_mode: Literal["polling", "webhook"] = "polling"
    webhook_url: str = ""
    webhook_port: int = 8443
    log_level: str = "INFO"
    fallback_max_chars: int = 4000

    @field_validator("telegram_allowed_chat_ids", mode="before")
    @classmethod
    def parse_chat_ids(cls, v: object) -> list[int]:
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v  # type: ignore[return-value]

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        numeric = getattr(logging, v.upper(), None)
        if not isinstance(numeric, int):
            raise ValueError(f"Invalid log level: {v}")
        return v.upper()

    @model_validator(mode="after")
    def validate_webhook_config(self) -> "Settings":
        if self.telegram_mode == "webhook" and not self.webhook_url:
            raise ValueError("WEBHOOK_URL must be set when TELEGRAM_MODE is 'webhook'")
        return self


def _load_from_env() -> Settings:
    """Build Settings from environment variables."""
    env = {}
    for field_name in Settings.model_fields:
        env_key = field_name.upper()
        val = os.environ.get(env_key)
        if val is not None:
            env[field_name] = val
    return Settings(**env)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton Settings instance."""
    return _load_from_env()
