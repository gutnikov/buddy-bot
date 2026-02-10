"""Tests for buddy_bot.config module."""

import pytest
from pydantic import ValidationError

from buddy_bot.config import Settings, get_settings


REQUIRED_ENV = {
    "ANTHROPIC_API_KEY": "sk-ant-test",
    "TELEGRAM_TOKEN": "7123456789:AAH-test",
    "TELEGRAM_ALLOWED_CHAT_IDS": "123456789",
    "OPENAI_API_KEY": "sk-test",
    "VOYAGE_API_KEY": "pa-test",
}


def test_load_required_variables():
    settings = Settings(**{k.lower(): v for k, v in REQUIRED_ENV.items()})
    assert settings.anthropic_api_key == "sk-ant-test"
    assert settings.telegram_token == "7123456789:AAH-test"
    assert settings.telegram_allowed_chat_ids == [123456789]
    assert settings.openai_api_key == "sk-test"
    assert settings.voyage_api_key == "pa-test"


def test_default_values():
    settings = Settings(**{k.lower(): v for k, v in REQUIRED_ENV.items()})
    assert settings.model == "claude-sonnet-4-5-20250929"
    assert settings.max_tokens == 4096
    assert settings.temperature == 0.7
    assert settings.history_turns == 20
    assert settings.history_max_chars == 500
    assert settings.history_db == "/data/history.db"
    assert settings.debounce_delay == 5
    assert settings.user_timezone == "UTC"
    assert settings.graphiti_url == "http://graphiti-mcp:8000"
    assert settings.tavily_api_key == ""
    assert settings.google_credentials_path == "/app/credentials/google_credentials.json"
    assert settings.telegram_mode == "polling"
    assert settings.webhook_url == ""
    assert settings.webhook_port == 8443
    assert settings.log_level == "INFO"
    assert settings.fallback_max_chars == 4000


def test_parse_chat_ids_comma_separated():
    env = {k.lower(): v for k, v in REQUIRED_ENV.items()}
    env["telegram_allowed_chat_ids"] = "123,456,789"
    settings = Settings(**env)
    assert settings.telegram_allowed_chat_ids == [123, 456, 789]


def test_parse_chat_ids_with_spaces():
    env = {k.lower(): v for k, v in REQUIRED_ENV.items()}
    env["telegram_allowed_chat_ids"] = " 123 , 456 "
    settings = Settings(**env)
    assert settings.telegram_allowed_chat_ids == [123, 456]


def test_missing_required_variable():
    with pytest.raises(ValidationError):
        Settings(
            anthropic_api_key="test",
            telegram_token="test",
            # telegram_allowed_chat_ids missing
            openai_api_key="test",
            voyage_api_key="test",
        )


def test_webhook_mode_requires_url():
    with pytest.raises(ValidationError, match="WEBHOOK_URL must be set"):
        Settings(
            **{k.lower(): v for k, v in REQUIRED_ENV.items()},
            telegram_mode="webhook",
            webhook_url="",
        )


def test_webhook_mode_with_url_succeeds():
    settings = Settings(
        **{k.lower(): v for k, v in REQUIRED_ENV.items()},
        telegram_mode="webhook",
        webhook_url="https://example.com/webhook",
    )
    assert settings.telegram_mode == "webhook"
    assert settings.webhook_url == "https://example.com/webhook"


def test_invalid_telegram_mode():
    with pytest.raises(ValidationError):
        Settings(
            **{k.lower(): v for k, v in REQUIRED_ENV.items()},
            telegram_mode="invalid",
        )


def test_valid_log_levels():
    for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        settings = Settings(
            **{k.lower(): v for k, v in REQUIRED_ENV.items()},
            log_level=level,
        )
        assert settings.log_level == level


def test_invalid_log_level():
    with pytest.raises(ValidationError, match="Invalid log level"):
        Settings(
            **{k.lower(): v for k, v in REQUIRED_ENV.items()},
            log_level="INVALID",
        )


def test_get_settings_from_env(monkeypatch):
    for k, v in REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.anthropic_api_key == "sk-ant-test"
    assert settings.telegram_allowed_chat_ids == [123456789]
    get_settings.cache_clear()


def test_get_settings_singleton(monkeypatch):
    for k, v in REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
    get_settings.cache_clear()
