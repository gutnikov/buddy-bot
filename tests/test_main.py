"""Tests for buddy_bot.main module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from buddy_bot.config import Settings


REQUIRED_SETTINGS = {
    "anthropic_api_key": "sk-test",
    "telegram_token": "tok",
    "telegram_allowed_chat_ids": [123],
    "openai_api_key": "sk-test",
    "voyage_api_key": "pa-test",
    "history_db": ":memory:",
}


@patch("buddy_bot.main.get_settings")
def test_buddy_bot_initialization(mock_get_settings, tmp_path):
    settings = Settings(**{**REQUIRED_SETTINGS, "history_db": str(tmp_path / "test.db")})
    mock_get_settings.return_value = settings

    from buddy_bot.main import BuddyBot

    bot = BuddyBot()
    assert bot._settings is settings
    assert bot._registry is not None
    assert bot._history is not None
    assert bot._graphiti is not None


@patch("buddy_bot.main.get_settings")
async def test_on_message_creates_buffer(mock_get_settings, tmp_path):
    settings = Settings(**{**REQUIRED_SETTINGS, "history_db": str(tmp_path / "test.db")})
    mock_get_settings.return_value = settings

    from buddy_bot.main import BuddyBot

    bot = BuddyBot()
    bot._processor = AsyncMock()

    event = {"text": "hello", "chat_id": "123", "from": "alex", "timestamp": "t"}

    # Mock the processing loop to avoid actual processing
    with patch.object(bot, "_processing_loop", new_callable=AsyncMock):
        await bot.on_message(event)

    assert "123" in bot._buffers
    assert not bot._buffers["123"].is_empty()


@patch("buddy_bot.main.get_settings")
async def test_shutdown_cleans_up(mock_get_settings, tmp_path):
    settings = Settings(**{**REQUIRED_SETTINGS, "history_db": str(tmp_path / "test.db")})
    mock_get_settings.return_value = settings

    from buddy_bot.main import BuddyBot

    bot = BuddyBot()
    bot._processor = AsyncMock()
    bot._app = MagicMock()
    bot._app.updater.stop = AsyncMock()
    bot._app.stop = AsyncMock()
    bot._app.shutdown = AsyncMock()

    await bot.shutdown()

    assert bot._shutdown_event.is_set()
    bot._processor.close.assert_called_once()
    bot._app.updater.stop.assert_called_once()


@patch("buddy_bot.main.get_settings")
async def test_processing_loop_requeues_on_failure(mock_get_settings, tmp_path):
    """Messages are re-queued after a processing failure."""
    settings = Settings(**{**REQUIRED_SETTINGS, "history_db": str(tmp_path / "test.db")})
    mock_get_settings.return_value = settings

    from buddy_bot.main import BuddyBot

    bot = BuddyBot()
    bot._processor = AsyncMock()
    bot._app = MagicMock()
    bot._app.bot = AsyncMock()

    call_count = 0

    async def mock_process(chat_id, events):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("transient failure")

    bot._processor.process = mock_process

    buf = bot._get_buffer("123")
    buf.add({"text": "hello", "chat_id": "123", "from": "alex", "timestamp": "t"})

    # Patch sleep to avoid real delays
    with patch("buddy_bot.main.asyncio.sleep", new_callable=AsyncMock):
        await bot._processing_loop("123")

    # First call failed, messages re-queued and processed on second try
    assert call_count == 2


@patch("buddy_bot.main.get_settings")
async def test_processing_loop_drops_after_3_failures(mock_get_settings, tmp_path):
    """After 3 consecutive failures, messages are dropped and user notified."""
    settings = Settings(**{**REQUIRED_SETTINGS, "history_db": str(tmp_path / "test.db")})
    mock_get_settings.return_value = settings

    from buddy_bot.main import BuddyBot

    bot = BuddyBot()
    bot._processor = AsyncMock()
    bot._processor.process = AsyncMock(side_effect=RuntimeError("persistent failure"))
    bot._app = MagicMock()
    bot._app.bot = AsyncMock()

    buf = bot._get_buffer("456")
    buf.add({"text": "hello", "chat_id": "456", "from": "alex", "timestamp": "t"})

    with patch("buddy_bot.main.asyncio.sleep", new_callable=AsyncMock):
        with patch("buddy_bot.bot.send_response", new_callable=AsyncMock) as mock_send:
            await bot._processing_loop("456")

            # User should be notified about the failure
            mock_send.assert_called_once()
            args = mock_send.call_args
            assert "trouble" in args[0][2].lower()
