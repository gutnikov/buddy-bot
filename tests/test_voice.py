"""Tests for voice message handling pipeline."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from buddy_bot.bot import create_application, extract_voice_event
from buddy_bot.config import Settings

REQUIRED_SETTINGS = {
    "telegram_token": "tok",
    "telegram_allowed_chat_ids": [123],
    "openai_api_key": "sk-test",
    "voyage_api_key": "pa-test",
    "speechkit_api_key": "sk-speech",
    "yandex_folder_id": "folder-123",
}


def _make_voice_update(
    duration: int = 5,
    chat_id: int = 123,
    message_id: int = 42,
    first_name: str = "Alex",
    is_bot: bool = False,
) -> MagicMock:
    """Create a mock Update with a voice attachment."""
    msg = MagicMock()
    msg.chat_id = chat_id
    msg.message_id = message_id
    msg.from_user.first_name = first_name
    msg.from_user.is_bot = is_bot
    msg.date = datetime(2026, 2, 10, 14, 30, 0, tzinfo=timezone.utc)
    msg.reply_text = AsyncMock()

    voice = MagicMock()
    voice.duration = duration
    voice.file_id = "voice-file-id"
    msg.voice = voice

    update = MagicMock()
    update.message = msg
    return update


def _make_bot_mock() -> AsyncMock:
    """Create a mock bot that can download voice files."""
    bot = AsyncMock()

    async def fake_download(buf):
        buf.write(b"fake-ogg-audio-data")

    file_mock = AsyncMock()
    file_mock.download_to_memory = AsyncMock(side_effect=fake_download)
    bot.get_file = AsyncMock(return_value=file_mock)
    bot.set_message_reaction = AsyncMock()
    return bot


@patch("buddy_bot.bot.recognize", return_value="распознанный текст")
async def test_successful_transcription(mock_recognize):
    """Voice message is transcribed and returned as event."""
    update = _make_voice_update(duration=10)
    bot = _make_bot_mock()
    settings = Settings(**REQUIRED_SETTINGS)
    http_client = AsyncMock(spec=httpx.AsyncClient)

    event = await extract_voice_event(update, bot, http_client, settings)

    assert event is not None
    assert event["text"] == "распознанный текст"
    assert event["source"] == "voice"
    assert event["voice_duration"] == 10
    assert event["chat_id"] == "123"
    bot.get_file.assert_called_once_with("voice-file-id")
    mock_recognize.assert_called_once()


@patch("buddy_bot.bot.recognize", return_value="распознанный текст")
async def test_voice_too_long(mock_recognize):
    """Voice messages over 30 seconds are rejected."""
    update = _make_voice_update(duration=31)
    bot = _make_bot_mock()
    settings = Settings(**REQUIRED_SETTINGS)
    http_client = AsyncMock(spec=httpx.AsyncClient)

    event = await extract_voice_event(update, bot, http_client, settings)

    assert event is None
    update.message.reply_text.assert_called_once_with(
        "Voice message too long, max 30 seconds."
    )
    mock_recognize.assert_not_called()


@patch("buddy_bot.bot.recognize", return_value="ok")
async def test_voice_exactly_30_seconds(mock_recognize):
    """Voice message exactly at 30s limit should be accepted."""
    update = _make_voice_update(duration=30)
    bot = _make_bot_mock()
    settings = Settings(**REQUIRED_SETTINGS)
    http_client = AsyncMock(spec=httpx.AsyncClient)

    event = await extract_voice_event(update, bot, http_client, settings)

    assert event is not None
    assert event["text"] == "ok"


@patch("buddy_bot.bot.recognize", return_value=None)
async def test_api_failure(mock_recognize):
    """API failure results in error reply."""
    update = _make_voice_update(duration=5)
    bot = _make_bot_mock()
    settings = Settings(**REQUIRED_SETTINGS)
    http_client = AsyncMock(spec=httpx.AsyncClient)

    event = await extract_voice_event(update, bot, http_client, settings)

    assert event is None
    update.message.reply_text.assert_called_once_with(
        "Could not transcribe voice message."
    )


@patch("buddy_bot.bot.recognize", return_value="")
async def test_empty_transcription(mock_recognize):
    """Empty transcription (silence/noise) results in appropriate reply."""
    update = _make_voice_update(duration=5)
    bot = _make_bot_mock()
    settings = Settings(**REQUIRED_SETTINGS)
    http_client = AsyncMock(spec=httpx.AsyncClient)

    event = await extract_voice_event(update, bot, http_client, settings)

    assert event is None
    update.message.reply_text.assert_called_once_with(
        "Could not recognize speech."
    )


async def test_bot_messages_ignored():
    """Voice messages from bots are ignored."""
    update = _make_voice_update(is_bot=True)
    bot = _make_bot_mock()
    settings = Settings(**REQUIRED_SETTINGS)
    http_client = AsyncMock(spec=httpx.AsyncClient)

    event = await extract_voice_event(update, bot, http_client, settings)

    assert event is None
    update.message.reply_text.assert_not_called()
    bot.get_file.assert_not_called()


async def test_no_voice_ignored():
    """Message without voice attachment is ignored."""
    update = _make_voice_update()
    update.message.voice = None
    bot = _make_bot_mock()
    settings = Settings(**REQUIRED_SETTINGS)
    http_client = AsyncMock(spec=httpx.AsyncClient)

    event = await extract_voice_event(update, bot, http_client, settings)

    assert event is None
    update.message.reply_text.assert_not_called()


async def test_voice_handler_not_registered_without_config():
    """Voice handler is not registered when SpeechKit is not configured."""
    on_message = AsyncMock()
    settings = Settings(**{
        **REQUIRED_SETTINGS,
        "speechkit_api_key": "",
    })

    app = create_application(
        "fake-token", [123], on_message,
        http_client=AsyncMock(spec=httpx.AsyncClient),
        settings=settings,
    )

    # Only the text/photo/document handler should be registered
    handlers = app.handlers[0]
    assert len(handlers) == 1


@patch("buddy_bot.bot.recognize", return_value="текст голоса")
async def test_voice_handler_registered_with_config(mock_recognize):
    """Voice handler IS registered when SpeechKit is configured."""
    on_message = AsyncMock()
    settings = Settings(**REQUIRED_SETTINGS)

    app = create_application(
        "fake-token", [123], on_message,
        http_client=AsyncMock(spec=httpx.AsyncClient),
        settings=settings,
    )

    # Both text and voice handlers should be registered
    handlers = app.handlers[0]
    assert len(handlers) == 2
