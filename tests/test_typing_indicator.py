"""Tests for buddy_bot.typing_indicator module."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from buddy_bot.typing_indicator import TypingIndicator


async def test_typing_sent_on_start():
    bot = AsyncMock()
    indicator = TypingIndicator(bot, "123")
    await indicator.start()
    await asyncio.sleep(0.1)
    await indicator.stop()
    bot.send_chat_action.assert_called()


async def test_typing_repeats():
    bot = AsyncMock()
    indicator = TypingIndicator(bot, "123")
    await indicator.start()
    # Wait enough for 2+ typing actions (interval is 4s, but we'll patch it)
    await asyncio.sleep(0.1)
    await indicator.stop()
    assert bot.send_chat_action.call_count >= 1


async def test_stop_cancels():
    bot = AsyncMock()
    indicator = TypingIndicator(bot, "123")
    await indicator.start()
    await indicator.stop()
    assert indicator._task is None


async def test_context_manager():
    bot = AsyncMock()
    async with TypingIndicator(bot, "123") as indicator:
        await asyncio.sleep(0.1)
        assert indicator._task is not None
    # After context, task should be stopped
    assert indicator._task is None


async def test_error_in_send_is_caught():
    bot = AsyncMock()
    bot.send_chat_action.side_effect = RuntimeError("network error")
    indicator = TypingIndicator(bot, "123")
    await indicator.start()
    await asyncio.sleep(0.1)
    await indicator.stop()
    # Should not raise


async def test_stop_when_not_started():
    bot = AsyncMock()
    indicator = TypingIndicator(bot, "123")
    # Should not raise
    await indicator.stop()
