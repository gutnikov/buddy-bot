"""Tests for buddy_bot.processor module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import pytest

from buddy_bot.config import Settings
from buddy_bot.processor import MessageProcessor, _is_retriable_api_error
from buddy_bot.retry import MaxRetriesExceeded


REQUIRED_SETTINGS = {
    "anthropic_api_key": "sk-test",
    "telegram_token": "tok",
    "telegram_allowed_chat_ids": [123],
    "openai_api_key": "sk-test",
    "voyage_api_key": "pa-test",
}


def _make_text_response(text="Hello!"):
    """Create a mock API response with text content."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    resp.stop_reason = "end_turn"
    return resp


def _make_tool_use_response(tool_name="get_episodes", tool_input=None, tool_id="toolu_123"):
    """Create a mock API response with a tool_use block."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = tool_name
    block.input = tool_input or {}
    block.id = tool_id
    resp = MagicMock()
    resp.content = [block]
    resp.stop_reason = "tool_use"
    return resp


@pytest.fixture
def processor():
    settings = Settings(**REQUIRED_SETTINGS)
    history = AsyncMock()
    history.get_recent_turns.return_value = []
    history.get_fallback.return_value = None
    registry = AsyncMock()
    registry.get_tool_definitions.return_value = []
    bot = AsyncMock()
    proc = MessageProcessor(settings, history, registry, bot)
    return proc, history, registry, bot


async def test_basic_text_response(processor):
    proc, history, registry, bot = processor
    events = [{"text": "hello", "from": "alex", "timestamp": "t"}]

    with patch.object(proc, "_client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=_make_text_response("Hi there!"))

        await proc.process("123", events)

        # Verify response sent
        bot.send_message.assert_called()
        # Verify turn saved
        history.save_turn.assert_called_once()
        call_args = history.save_turn.call_args
        assert call_args[0][0] == "123"  # chat_id
        assert call_args[0][2] == "Hi there!"  # bot_response


async def test_tool_use_loop(processor):
    proc, history, registry, bot = processor
    events = [{"text": "what episodes?", "from": "alex", "timestamp": "t"}]

    tool_resp = _make_tool_use_response("get_episodes", {})
    text_resp = _make_text_response("Here are your episodes.")

    with patch.object(proc, "_client") as mock_client:
        mock_client.messages.create = AsyncMock(side_effect=[tool_resp, text_resp])
        registry.dispatch = AsyncMock(return_value='[{"name": "ep1"}]')

        await proc.process("123", events)

        # Tool was dispatched
        registry.dispatch.assert_called_once_with("get_episodes", {})
        # Response sent
        bot.send_message.assert_called()


async def test_turn_saved_after_success(processor):
    proc, history, registry, bot = processor
    events = [{"text": "test msg", "from": "alex", "timestamp": "t"}]

    with patch.object(proc, "_client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=_make_text_response("reply"))
        await proc.process("123", events)

    history.save_turn.assert_called_once()
    history.clear_fallback.assert_called_once_with("123")


async def test_fallback_saved_on_error(processor):
    proc, history, registry, bot = processor
    events = [{"text": "failing", "from": "alex", "timestamp": "t"}]

    with patch.object(proc, "_client") as mock_client:
        mock_client.messages.create = AsyncMock(side_effect=RuntimeError("API down"))

        with pytest.raises(RuntimeError):
            await proc.process("123", events)

    history.save_fallback.assert_called_once()


async def test_serial_execution(processor):
    """Concurrent calls for same chat_id should be serialized."""
    proc, history, registry, bot = processor
    events = [{"text": "msg", "from": "alex", "timestamp": "t"}]

    call_order = []

    async def slow_create(*args, **kwargs):
        call_order.append("start")
        await asyncio.sleep(0.1)
        call_order.append("end")
        return _make_text_response("ok")

    with patch.object(proc, "_client") as mock_client:
        mock_client.messages.create = slow_create

        await asyncio.gather(
            proc.process("123", events),
            proc.process("123", events),
        )

    # Should be start-end-start-end (serialized), not start-start-end-end
    assert call_order == ["start", "end", "start", "end"]


def test_is_retriable_rate_limit():
    exc = anthropic.RateLimitError.__new__(anthropic.RateLimitError)
    assert _is_retriable_api_error(exc) is True


def test_is_retriable_internal_server():
    exc = anthropic.InternalServerError.__new__(anthropic.InternalServerError)
    assert _is_retriable_api_error(exc) is True


def test_is_retriable_overloaded_529():
    exc = MagicMock(spec=anthropic.APIStatusError)
    exc.status_code = 529
    # Need isinstance check to work
    exc.__class__ = anthropic.APIStatusError
    assert _is_retriable_api_error(exc) is True


def test_is_not_retriable_bad_request():
    assert _is_retriable_api_error(ValueError("bad")) is False


async def test_graphiti_health_check_called(processor):
    """Graphiti health check runs before API call."""
    proc, history, registry, bot = processor
    graphiti = AsyncMock()
    graphiti.health_check.return_value = True
    proc._graphiti = graphiti
    events = [{"text": "hi", "from": "alex", "timestamp": "t"}]

    with patch.object(proc, "_client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=_make_text_response("ok"))
        await proc.process("123", events)

    graphiti.health_check.assert_called_once()


async def test_graphiti_unavailable_proceeds(processor):
    """Processing continues when Graphiti is unhealthy."""
    proc, history, registry, bot = processor
    graphiti = AsyncMock()
    graphiti.health_check.return_value = False
    proc._graphiti = graphiti
    events = [{"text": "hi", "from": "alex", "timestamp": "t"}]

    with patch.object(proc, "_client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=_make_text_response("ok"))
        await proc.process("123", events)

    # Should still complete successfully
    bot.send_message.assert_called()
    history.save_turn.assert_called_once()


async def test_api_call_retries_on_rate_limit(processor):
    """Rate limit errors trigger retries via retry_with_backoff."""
    proc, history, registry, bot = processor
    events = [{"text": "hi", "from": "alex", "timestamp": "t"}]

    rate_exc = anthropic.RateLimitError.__new__(anthropic.RateLimitError)

    with patch.object(proc, "_client") as mock_client:
        mock_client.messages.create = AsyncMock(
            side_effect=[rate_exc, _make_text_response("ok")]
        )
        with patch("buddy_bot.retry.asyncio.sleep", new_callable=AsyncMock):
            await proc.process("123", events)

    bot.send_message.assert_called()


async def test_api_call_retries_on_5xx(processor):
    """5xx errors trigger retries."""
    proc, history, registry, bot = processor
    events = [{"text": "hi", "from": "alex", "timestamp": "t"}]

    server_exc = anthropic.InternalServerError.__new__(anthropic.InternalServerError)

    with patch.object(proc, "_client") as mock_client:
        mock_client.messages.create = AsyncMock(
            side_effect=[server_exc, _make_text_response("ok")]
        )
        with patch("buddy_bot.retry.asyncio.sleep", new_callable=AsyncMock):
            await proc.process("123", events)

    bot.send_message.assert_called()


async def test_fallback_context_round_trip():
    """Fallback saved on error, loaded on next call, cleared on success."""
    settings = Settings(**REQUIRED_SETTINGS)
    history = AsyncMock()
    history.get_recent_turns.return_value = []
    # First call: no fallback
    history.get_fallback.side_effect = [None, "Processing failed for messages: ['hello']"]
    registry = AsyncMock()
    registry.get_tool_definitions.return_value = []
    bot = AsyncMock()
    proc = MessageProcessor(settings, history, registry, bot)

    events = [{"text": "hello", "from": "alex", "timestamp": "t"}]

    # First call fails — fallback saved
    with patch.object(proc, "_client") as mock_client:
        mock_client.messages.create = AsyncMock(side_effect=RuntimeError("fail"))
        with pytest.raises(RuntimeError):
            await proc.process("123", events)

    history.save_fallback.assert_called_once()

    # Second call succeeds — fallback loaded and cleared
    history.save_fallback.reset_mock()
    with patch.object(proc, "_client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=_make_text_response("ok"))
        await proc.process("123", events)

    history.get_fallback.assert_called_with("123")
    history.clear_fallback.assert_called_with("123")
