"""Tests for buddy_bot.mcp_server module."""

import json
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest


@pytest.fixture(autouse=True)
def mcp_env(monkeypatch):
    """Set environment variables for the MCP server."""
    monkeypatch.setenv("USER_TIMEZONE", "UTC")
    import buddy_bot.mcp_server as mod
    mod.USER_TIMEZONE = "UTC"


def test_tool_list():
    """Tools should include get_current_time and notify_progress."""
    from buddy_bot.mcp_server import TOOLS
    assert len(TOOLS) == 2
    names = [t.name for t in TOOLS]
    assert "get_current_time" in names
    assert "notify_progress" in names


async def test_get_current_time():
    """get_current_time should return datetime info."""
    from buddy_bot.mcp_server import _handle_get_current_time
    result = json.loads(await _handle_get_current_time({"timezone": "UTC"}))
    assert "datetime" in result
    assert result["timezone"] == "UTC"
    assert "date" in result
    assert "time" in result


async def test_get_current_time_invalid_tz():
    from buddy_bot.mcp_server import _handle_get_current_time
    result = json.loads(await _handle_get_current_time({"timezone": "Invalid/Zone"}))
    assert "error" in result


async def test_call_tool_dispatches():
    """call_tool() should dispatch to the correct handler."""
    from buddy_bot.mcp_server import call_tool
    result = await call_tool("get_current_time", {"timezone": "UTC"})
    assert len(result) == 1
    parsed = json.loads(result[0].text)
    assert "datetime" in parsed


async def test_call_tool_unknown():
    """call_tool() with unknown name returns error."""
    from buddy_bot.mcp_server import call_tool
    result = await call_tool("nonexistent_tool", {})
    assert len(result) == 1
    parsed = json.loads(result[0].text)
    assert "error" in parsed
    assert "Unknown tool" in parsed["error"]


async def test_list_tools_returns_all():
    """list_tools() returns 2 tools."""
    from buddy_bot.mcp_server import list_tools
    tools = await list_tools()
    assert len(tools) == 2


async def test_notify_progress_success():
    """notify_progress sends message via Telegram API and returns success."""
    import buddy_bot.mcp_server as mod
    from buddy_bot.mcp_server import _handle_notify_progress
    mod.TELEGRAM_TOKEN = "fake-token"

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = b'{"ok":true}'
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("buddy_bot.mcp_server.urlopen", return_value=mock_response) as mock_urlopen:
        result = json.loads(await _handle_notify_progress({
            "chat_id": "123",
            "message": "On it!",
        }))

    assert result["status"] == "sent"
    mock_urlopen.assert_called_once()
    req = mock_urlopen.call_args[0][0]
    assert "api.telegram.org" in req.full_url
    assert b"On it!" in req.data


async def test_notify_progress_missing_token():
    """notify_progress returns error when TELEGRAM_TOKEN is not set."""
    import buddy_bot.mcp_server as mod
    from buddy_bot.mcp_server import _handle_notify_progress
    mod.TELEGRAM_TOKEN = ""

    result = json.loads(await _handle_notify_progress({
        "chat_id": "123",
        "message": "Hello",
    }))
    assert "error" in result


async def test_notify_progress_missing_params():
    """notify_progress returns error for missing required params."""
    import buddy_bot.mcp_server as mod
    from buddy_bot.mcp_server import _handle_notify_progress
    mod.TELEGRAM_TOKEN = "fake-token"

    result = json.loads(await _handle_notify_progress({}))
    assert "error" in result


async def test_notify_progress_http_failure():
    """notify_progress returns error on HTTP failure."""
    import buddy_bot.mcp_server as mod
    from buddy_bot.mcp_server import _handle_notify_progress
    mod.TELEGRAM_TOKEN = "fake-token"

    with patch("buddy_bot.mcp_server.urlopen", side_effect=URLError("fail")):
        result = json.loads(await _handle_notify_progress({
            "chat_id": "123",
            "message": "test",
        }))
    assert "error" in result
