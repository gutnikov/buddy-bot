"""Tests for buddy_bot.mcp_server module."""

import json

import pytest


@pytest.fixture(autouse=True)
def mcp_env(monkeypatch):
    """Set environment variables for the MCP server."""
    monkeypatch.setenv("USER_TIMEZONE", "UTC")
    import buddy_bot.mcp_server as mod
    mod.USER_TIMEZONE = "UTC"


def test_tool_list():
    """Only 1 tool should be defined."""
    from buddy_bot.mcp_server import TOOLS
    assert len(TOOLS) == 1
    assert TOOLS[0].name == "get_current_time"


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
    """list_tools() returns 1 tool."""
    from buddy_bot.mcp_server import list_tools
    tools = await list_tools()
    assert len(tools) == 1
