"""Tests for buddy_bot.executor module."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from buddy_bot.config import Settings
from buddy_bot.executor import ClaudeExecutor
from buddy_bot.history import HistoryStore

REQUIRED_SETTINGS = {
    "telegram_token": "tok",
    "telegram_allowed_chat_ids": [123],
    "openai_api_key": "sk-test",
    "voyage_api_key": "pa-test",
}


@pytest.fixture
def components(tmp_path):
    settings = Settings(**{**REQUIRED_SETTINGS, "history_db": str(tmp_path / "test.db")})
    history = HistoryStore(str(tmp_path / "test.db"))
    bot = AsyncMock()
    executor = ClaudeExecutor(settings, history, bot)
    return {"settings": settings, "history": history, "bot": bot, "executor": executor}


def _make_jsonl(*lines):
    """Create bytes from JSONL messages."""
    return b"\n".join(json.dumps(line).encode() for line in lines) + b"\n"


def _make_mock_process(stdout_data: bytes, returncode: int = 0, stderr_data: bytes = b""):
    """Create a mock subprocess with given stdout/stderr/returncode."""
    proc = AsyncMock()
    proc.stdout = AsyncMock()

    # Make readline() yield lines then b""
    lines = [line + b"\n" for line in stdout_data.split(b"\n") if line]
    lines.append(b"")  # EOF
    proc.stdout.readline = AsyncMock(side_effect=lines)

    proc.stderr = AsyncMock()
    proc.stderr.read = AsyncMock(return_value=stderr_data)
    proc.returncode = returncode
    proc.wait = AsyncMock(return_value=returncode)
    proc.kill = MagicMock()
    # For _resume_session which uses communicate()
    proc.communicate = AsyncMock(return_value=(stdout_data, stderr_data))
    return proc


async def test_process_happy_path(components):
    """Full pipeline: prompt → claude -p → JSONL → response → history saved."""
    executor = components["executor"]
    bot = components["bot"]
    history = components["history"]

    events = [{"text": "hello", "from": "alex", "timestamp": "2026-02-10T12:00:00Z"}]

    stdout_data = _make_jsonl(
        {"type": "system", "session_id": "sess-123"},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "thinking"}]}},
        {"type": "result", "result": "Hi Alex! How are you?"},
    )

    mock_proc = _make_mock_process(stdout_data)

    with patch("buddy_bot.executor.asyncio.create_subprocess_exec", return_value=mock_proc):
        await executor.process("123", events)

    # Response sent to Telegram
    bot.send_message.assert_called()
    call_args = bot.send_message.call_args
    assert "Hi Alex" in call_args.kwargs.get("text", call_args[1].get("text", ""))

    # Turn saved to history
    turns = await history.get_recent_turns("123")
    assert len(turns) == 1
    assert turns[0].user_text == "hello"
    assert "Hi Alex" in turns[0].bot_response


async def test_process_with_tool_use(components):
    """Tool use blocks are parsed from assistant messages."""
    executor = components["executor"]
    bot = components["bot"]

    events = [{"text": "what time is it?", "from": "alex", "timestamp": "t"}]

    stdout_data = _make_jsonl(
        {"type": "system", "session_id": "sess-456"},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "mcp__buddy-bot-tools__get_current_time", "id": "t1"}
        ]}},
        {"type": "result", "result": "It's 2:30 PM!"},
    )

    mock_proc = _make_mock_process(stdout_data)

    with patch("buddy_bot.executor.asyncio.create_subprocess_exec", return_value=mock_proc):
        await executor.process("123", events)

    bot.send_message.assert_called()


async def test_empty_result_triggers_resume(components):
    """Empty result should trigger session resume."""
    executor = components["executor"]
    bot = components["bot"]

    events = [{"text": "test", "from": "alex", "timestamp": "t"}]

    # First call: empty result with session_id
    stdout_data = _make_jsonl(
        {"type": "system", "session_id": "sess-789"},
        {"type": "result", "result": ""},
    )
    mock_proc = _make_mock_process(stdout_data)

    # Resume returns actual text
    resume_stdout = json.dumps({"result": "Here's my response!", "session_id": "sess-789"}).encode()
    resume_proc = _make_mock_process(resume_stdout)

    with patch("buddy_bot.executor.asyncio.create_subprocess_exec", side_effect=[mock_proc, resume_proc]):
        await executor.process("123", events)

    bot.send_message.assert_called()
    call_args = bot.send_message.call_args
    assert "Here's my response" in call_args.kwargs.get("text", call_args[1].get("text", ""))


async def test_process_failure_saves_fallback(components):
    """Processing failure saves fallback context."""
    executor = components["executor"]
    history = components["history"]

    events = [{"text": "test fallback", "from": "alex", "timestamp": "t"}]

    mock_proc = _make_mock_process(b"", returncode=1, stderr_data=b"CLI error")

    with patch("buddy_bot.executor.asyncio.create_subprocess_exec", return_value=mock_proc):
        with pytest.raises(RuntimeError):
            await executor.process("123", events)

    # Fallback should be saved
    row = history._conn.execute(
        "SELECT stdout FROM fallback_context WHERE chat_id = ?", ("123",)
    ).fetchone()
    assert row is not None
    assert "test fallback" in row["stdout"]


async def test_timeout_kills_process(components):
    """CLI timeout kills the subprocess and raises."""
    settings = components["settings"]
    # Override timeout to something very short
    executor = ClaudeExecutor(
        Settings(**{**REQUIRED_SETTINGS, "history_db": settings.history_db, "claude_timeout": 1}),
        components["history"],
        components["bot"],
    )

    events = [{"text": "test", "from": "alex", "timestamp": "t"}]

    async def hang_forever():
        await asyncio.sleep(999)
        return b""

    proc = AsyncMock()
    proc.stdout = AsyncMock()
    proc.stdout.readline = hang_forever
    proc.stderr = AsyncMock()
    proc.stderr.read = AsyncMock(return_value=b"")
    proc.returncode = -9
    proc.wait = AsyncMock(return_value=-9)
    proc.kill = MagicMock()

    with patch("buddy_bot.executor.asyncio.create_subprocess_exec", return_value=proc):
        with pytest.raises(RuntimeError, match="timed out"):
            await executor.process("123", events)


async def test_build_command(components):
    """Verify the claude CLI command structure."""
    executor = components["executor"]
    cmd = executor._build_command("Hello world")

    assert cmd[0] == "claude"
    assert "-p" in cmd
    assert "Hello world" in cmd
    assert "--output-format" in cmd
    assert "stream-json" in cmd
    assert "--verbose" in cmd
    assert "--model" in cmd
    assert "--mcp-config" in cmd
    assert "--allowedTools" in cmd
    assert "mcp__*" in cmd


async def test_per_chat_locking(components):
    """Verify that processing is serialized per chat_id."""
    executor = components["executor"]
    call_order = []

    async def mock_process_impl(chat_id, events):
        call_order.append(f"start-{len(call_order)+1}")
        await asyncio.sleep(0.05)
        call_order.append(f"end-{len(call_order)+1}")

    with patch.object(executor, "_process_impl", side_effect=mock_process_impl):
        await asyncio.gather(
            executor.process("123", [{"text": "a"}]),
            executor.process("123", [{"text": "b"}]),
        )

    # Should be serialized
    assert call_order[0].startswith("start")
    assert call_order[1].startswith("end")
    assert call_order[2].startswith("start")
    assert call_order[3].startswith("end")


async def test_non_json_lines_ignored(components):
    """Non-JSON lines in stdout are safely ignored."""
    executor = components["executor"]
    bot = components["bot"]

    events = [{"text": "test", "from": "alex", "timestamp": "t"}]

    # Mix of JSON and non-JSON lines
    lines = [
        b"Some startup message\n",
        json.dumps({"type": "system", "session_id": "s1"}).encode() + b"\n",
        b"Warning: something\n",
        json.dumps({"type": "result", "result": "Got it!"}).encode() + b"\n",
        b"",
    ]

    proc = AsyncMock()
    proc.stdout = AsyncMock()
    proc.stdout.readline = AsyncMock(side_effect=lines)
    proc.stderr = AsyncMock()
    proc.stderr.read = AsyncMock(return_value=b"")
    proc.returncode = 0
    proc.wait = AsyncMock(return_value=0)

    with patch("buddy_bot.executor.asyncio.create_subprocess_exec", return_value=proc):
        await executor.process("123", events)

    bot.send_message.assert_called()
    call_args = bot.send_message.call_args
    assert "Got it!" in call_args.kwargs.get("text", call_args[1].get("text", ""))


async def test_close_is_noop(components):
    """Close should work without error."""
    executor = components["executor"]
    await executor.close()
