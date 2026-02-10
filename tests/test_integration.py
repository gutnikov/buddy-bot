"""Integration tests: end-to-end message processing pipeline.

These tests verify the full pipeline with mocked external services
(Telegram, Anthropic, Graphiti) but real internal components
(SQLite history, message buffer, prompt builder, tool registry).
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from buddy_bot.config import Settings
from buddy_bot.graphiti import GraphitiClient
from buddy_bot.history import HistoryStore
from buddy_bot.processor import MessageProcessor
from buddy_bot.tools.memory import register_memory_tools
from buddy_bot.tools.registry import ToolRegistry

REQUIRED_SETTINGS = {
    "anthropic_api_key": "sk-test",
    "telegram_token": "tok",
    "telegram_allowed_chat_ids": [123],
    "openai_api_key": "sk-test",
    "voyage_api_key": "pa-test",
}


def _make_text_response(text="Hello!"):
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    resp.stop_reason = "end_turn"
    return resp


def _make_tool_use_response(tool_name, tool_input=None, tool_id="toolu_1"):
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
def components(tmp_path):
    """Create real internal components with mocked externals."""
    settings = Settings(**{**REQUIRED_SETTINGS, "history_db": str(tmp_path / "test.db")})
    history = HistoryStore(str(tmp_path / "test.db"))
    graphiti = AsyncMock(spec=GraphitiClient)
    graphiti.health_check.return_value = True
    graphiti.get_episodes.return_value = []
    graphiti.search_facts.return_value = []
    graphiti.search_nodes.return_value = []
    graphiti.add_memory.return_value = {}

    registry = ToolRegistry()
    register_memory_tools(registry, graphiti)

    bot = AsyncMock()
    proc = MessageProcessor(settings, history, registry, bot, graphiti=graphiti)

    return {
        "settings": settings,
        "history": history,
        "graphiti": graphiti,
        "registry": registry,
        "bot": bot,
        "processor": proc,
    }


async def test_happy_path_simple_message(components):
    """Full pipeline: message → prompt → API → tool calls → response → save."""
    proc = components["processor"]
    bot = components["bot"]
    history = components["history"]
    graphiti = components["graphiti"]

    events = [{"text": "hello", "from": "alex", "timestamp": "2026-02-10T12:00:00Z"}]

    # Claude first calls get_episodes, then search_memory_facts, then responds
    tool_resp_1 = _make_tool_use_response("get_episodes", {"group_ids": ["main"], "max_episodes": 5})
    tool_resp_2 = _make_tool_use_response("search_memory_facts", {"query": "pending items", "group_ids": ["main"]}, tool_id="toolu_2")
    text_resp = _make_text_response("Hi Alex! How are you?")

    with patch.object(proc, "_client") as mock_client:
        mock_client.messages.create = AsyncMock(
            side_effect=[tool_resp_1, tool_resp_2, text_resp]
        )
        await proc.process("123", events)

    # Response sent to Telegram
    bot.send_message.assert_called()
    call_args = bot.send_message.call_args
    assert "Hi Alex" in call_args.kwargs.get("text", call_args[1].get("text", ""))

    # Turn saved to history
    turns = await history.get_recent_turns("123")
    assert len(turns) == 1
    assert turns[0].user_text == "hello"
    assert "Hi Alex" in turns[0].bot_response


async def test_multi_message_batch(components):
    """Multiple messages batched into single prompt → single API call → single response."""
    proc = components["processor"]
    bot = components["bot"]
    history = components["history"]

    events = [
        {"text": "hey", "from": "alex", "timestamp": "2026-02-10T12:00:00Z"},
        {"text": "how's the weather?", "from": "alex", "timestamp": "2026-02-10T12:00:02Z"},
        {"text": "also check my calendar", "from": "alex", "timestamp": "2026-02-10T12:00:04Z"},
    ]

    text_resp = _make_text_response("It's sunny! And your calendar is clear.")

    with patch.object(proc, "_client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=text_resp)
        await proc.process("123", events)

    # Verify single API call with all messages in prompt
    assert mock_client.messages.create.call_count == 1
    api_call = mock_client.messages.create.call_args
    user_content = api_call.kwargs.get("messages", api_call[1].get("messages", []))[0]["content"]
    assert "hey" in user_content
    assert "how's the weather" in user_content
    assert "check my calendar" in user_content

    # Verify turn saved with all messages joined
    turns = await history.get_recent_turns("123")
    assert len(turns) == 1
    assert "hey" in turns[0].user_text
    assert "weather" in turns[0].user_text


async def test_tool_use_cycle(components):
    """Tool use: Claude calls get_episodes → gets result → returns text."""
    proc = components["processor"]
    bot = components["bot"]
    graphiti = components["graphiti"]

    events = [{"text": "what did we talk about?", "from": "alex", "timestamp": "t"}]

    graphiti.get_episodes.return_value = [{"content": "Discussed project deadline"}]

    tool_resp = _make_tool_use_response(
        "get_episodes", {"group_ids": ["main"], "max_episodes": 5}
    )
    text_resp = _make_text_response("We talked about the project deadline.")

    with patch.object(proc, "_client") as mock_client:
        mock_client.messages.create = AsyncMock(side_effect=[tool_resp, text_resp])
        await proc.process("123", events)

    # Tool was dispatched to graphiti
    graphiti.get_episodes.assert_called()
    # Final text response sent
    bot.send_message.assert_called()


async def test_memory_save(components):
    """Claude calls add_memory → Graphiti receives episode data."""
    proc = components["processor"]
    graphiti = components["graphiti"]

    events = [{"text": "remember that I like coffee", "from": "alex", "timestamp": "t"}]

    tool_resp = _make_tool_use_response(
        "add_memory",
        {
            "name": "coffee preference",
            "episode_body": "Alex mentioned they like coffee",
            "group_id": "main",
            "source": "text",
        },
    )
    text_resp = _make_text_response("I'll remember that you like coffee!")

    with patch.object(proc, "_client") as mock_client:
        mock_client.messages.create = AsyncMock(side_effect=[tool_resp, text_resp])
        await proc.process("123", events)

    graphiti.add_memory.assert_called_once_with(
        "coffee preference",
        "Alex mentioned they like coffee",
        "main",
        "text",
    )


async def test_error_recovery_with_retry(components):
    """API 429 → retry → success → response delivered."""
    proc = components["processor"]
    bot = components["bot"]
    history = components["history"]

    events = [{"text": "hi", "from": "alex", "timestamp": "t"}]

    import anthropic
    rate_exc = anthropic.RateLimitError.__new__(anthropic.RateLimitError)

    with patch.object(proc, "_client") as mock_client:
        mock_client.messages.create = AsyncMock(
            side_effect=[rate_exc, _make_text_response("Hello!")]
        )
        with patch("buddy_bot.retry.asyncio.sleep", new_callable=AsyncMock):
            await proc.process("123", events)

    # Response still delivered despite initial 429
    bot.send_message.assert_called()
    turns = await history.get_recent_turns("123")
    assert len(turns) == 1


async def test_fallback_context_round_trip(components):
    """Failure saves fallback → next call includes it in prompt → clears on success."""
    proc = components["processor"]
    history = components["history"]

    events = [{"text": "test fallback", "from": "alex", "timestamp": "t"}]

    # First call: API fails
    with patch.object(proc, "_client") as mock_client:
        mock_client.messages.create = AsyncMock(side_effect=RuntimeError("API down"))
        with pytest.raises(RuntimeError):
            await proc.process("123", events)

    # Fallback should be saved — peek without consuming by checking the DB directly
    row = history._conn.execute(
        "SELECT stdout FROM fallback_context WHERE chat_id = ?", ("123",)
    ).fetchone()
    assert row is not None
    assert "test fallback" in row["stdout"]

    # Second call: succeeds, fallback consumed and included in prompt
    with patch.object(proc, "_client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=_make_text_response("ok"))
        await proc.process("123", events)

    # Verify prompt included fallback (second call's messages arg)
    api_call = mock_client.messages.create.call_args
    user_content = api_call.kwargs.get("messages", api_call[1].get("messages", []))[0]["content"]
    assert "retry after failure" in user_content.lower() or "processing failed" in user_content.lower()

    # Fallback should be cleared after success
    row_after = history._conn.execute(
        "SELECT stdout FROM fallback_context WHERE chat_id = ?", ("123",)
    ).fetchone()
    assert row_after is None


async def test_concurrent_messages_during_processing(components):
    """Second message queued while first is processing, processed after first completes."""
    proc = components["processor"]
    bot = components["bot"]
    history = components["history"]

    events_1 = [{"text": "first message", "from": "alex", "timestamp": "t1"}]
    events_2 = [{"text": "second message", "from": "alex", "timestamp": "t2"}]

    call_count = 0
    call_order = []

    async def mock_create(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        call_order.append(f"start-{call_count}")
        await asyncio.sleep(0.05)  # Simulate processing time
        call_order.append(f"end-{call_count}")
        return _make_text_response(f"response {call_count}")

    with patch.object(proc, "_client") as mock_client:
        mock_client.messages.create = mock_create
        # Process both concurrently — serialized by per-chat lock
        await asyncio.gather(
            proc.process("123", events_1),
            proc.process("123", events_2),
        )

    # Both processed, serialized (start-end-start-end, not interleaved)
    assert call_order == ["start-1", "end-1", "start-2", "end-2"]

    # Both turns saved
    turns = await history.get_recent_turns("123")
    assert len(turns) == 2
