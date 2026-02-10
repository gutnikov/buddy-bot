"""Tests for buddy_bot.bot module."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from buddy_bot.bot import extract_event, is_authorized, split_message, send_response


def test_authorized_chat():
    assert is_authorized(123, [123, 456])


def test_unauthorized_chat():
    assert not is_authorized(999, [123, 456])


def _make_update(text="hello", chat_id=123, message_id=42, first_name="Alex"):
    msg = MagicMock()
    msg.text = text
    msg.caption = None
    msg.chat_id = chat_id
    msg.message_id = message_id
    msg.from_user.first_name = first_name
    msg.date = datetime(2026, 2, 10, 14, 30, 0, tzinfo=timezone.utc)
    update = MagicMock()
    update.message = msg
    return update


def test_extract_event_text():
    update = _make_update(text="hello world")
    event = extract_event(update)
    assert event is not None
    assert event["text"] == "hello world"
    assert event["from"] == "Alex"
    assert event["chat_id"] == "123"
    assert event["message_id"] == 42
    assert "2026-02-10" in event["timestamp"]


def test_extract_event_photo_caption():
    update = _make_update(text=None)
    update.message.text = None
    update.message.caption = "nice photo"
    event = extract_event(update)
    assert event is not None
    assert event["text"] == "nice photo"


def test_extract_event_no_text():
    update = _make_update()
    update.message.text = None
    update.message.caption = None
    event = extract_event(update)
    assert event is None


def test_split_message_short():
    chunks = split_message("short message")
    assert chunks == ["short message"]


def test_split_message_at_paragraph():
    text = "a" * 4000 + "\n\n" + "b" * 100
    chunks = split_message(text, max_length=4096)
    assert len(chunks) == 2
    assert chunks[0] == "a" * 4000
    assert chunks[1] == "b" * 100


def test_split_message_hard_split():
    text = "a" * 8000
    chunks = split_message(text, max_length=4096)
    assert len(chunks) == 2
    assert len(chunks[0]) == 4096
    assert len(chunks[1]) == 8000 - 4096


async def test_send_response_splits_long():
    bot = AsyncMock()
    long_text = "word " * 1000  # ~5000 chars
    await send_response(bot, "123", long_text)
    assert bot.send_message.call_count >= 2


async def test_send_response_single_message():
    bot = AsyncMock()
    await send_response(bot, "123", "short")
    bot.send_message.assert_called_once()
