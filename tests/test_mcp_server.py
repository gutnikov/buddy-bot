"""Tests for buddy_bot.mcp_server module."""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def mcp_env(monkeypatch, tmp_path):
    """Set environment variables for the MCP server."""
    monkeypatch.setenv("HISTORY_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("USER_TIMEZONE", "UTC")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "")
    # Reset module-level singletons
    import buddy_bot.mcp_server as mod
    mod._todo_store = None
    mod._google_auth = None
    mod.HISTORY_DB = str(tmp_path / "test.db")
    mod.USER_TIMEZONE = "UTC"
    mod.TAVILY_API_KEY = ""
    mod.PERPLEXITY_API_KEY = ""


def test_tool_list():
    """All 13 tools should be defined."""
    from buddy_bot.mcp_server import TOOLS
    assert len(TOOLS) == 13
    names = {t.name for t in TOOLS}
    expected = {
        "todo_add", "todo_list", "todo_complete", "todo_delete",
        "calendar_list_events", "calendar_create_event", "calendar_delete_event",
        "email_list_messages", "email_read_message", "email_send_message",
        "web_search", "perplexity_search", "get_current_time",
    }
    assert names == expected


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


async def test_todo_add_and_list():
    """Todo add and list should work via handlers."""
    from buddy_bot.mcp_server import _handle_todo_add, _handle_todo_list

    add_result = json.loads(await _handle_todo_add({
        "chat_id": "test-123",
        "title": "Buy milk",
        "priority": "high",
    }))
    assert add_result["status"] == "created"
    assert add_result["title"] == "Buy milk"
    assert "todo_id" in add_result

    list_result = json.loads(await _handle_todo_list({"chat_id": "test-123"}))
    assert len(list_result) == 1
    assert list_result[0]["title"] == "Buy milk"


async def test_todo_complete():
    from buddy_bot.mcp_server import _handle_todo_add, _handle_todo_complete

    add_result = json.loads(await _handle_todo_add({
        "chat_id": "test-456",
        "title": "Test task",
    }))
    todo_id = add_result["todo_id"]

    complete_result = json.loads(await _handle_todo_complete({
        "chat_id": "test-456",
        "todo_id": todo_id,
    }))
    assert complete_result["status"] == "completed"


async def test_todo_delete():
    from buddy_bot.mcp_server import _handle_todo_add, _handle_todo_delete, _handle_todo_list

    add_result = json.loads(await _handle_todo_add({
        "chat_id": "test-789",
        "title": "To delete",
    }))
    todo_id = add_result["todo_id"]

    delete_result = json.loads(await _handle_todo_delete({
        "chat_id": "test-789",
        "todo_id": todo_id,
    }))
    assert delete_result["status"] == "deleted"

    list_result = json.loads(await _handle_todo_list({"chat_id": "test-789"}))
    assert len(list_result) == 0


async def test_todo_chat_isolation():
    """Todos are isolated per chat_id."""
    from buddy_bot.mcp_server import _handle_todo_add, _handle_todo_list

    await _handle_todo_add({"chat_id": "aaa", "title": "Task AAA"})
    await _handle_todo_add({"chat_id": "bbb", "title": "Task BBB"})

    result_a = json.loads(await _handle_todo_list({"chat_id": "aaa"}))
    result_b = json.loads(await _handle_todo_list({"chat_id": "bbb"}))

    assert len(result_a) == 1
    assert result_a[0]["title"] == "Task AAA"
    assert len(result_b) == 1
    assert result_b[0]["title"] == "Task BBB"


async def test_web_search_not_configured():
    from buddy_bot.mcp_server import _handle_web_search
    result = json.loads(await _handle_web_search({"query": "test"}))
    assert "error" in result
    assert "not configured" in result["error"]


async def test_perplexity_search_not_configured():
    from buddy_bot.mcp_server import _handle_perplexity_search
    result = json.loads(await _handle_perplexity_search({"query": "test"}))
    assert "error" in result
    assert "not configured" in result["error"]


async def test_web_search_with_mock_api():
    import buddy_bot.mcp_server as mod
    mod.TAVILY_API_KEY = "tvly-test"

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "results": [
            {"title": "Result 1", "url": "https://example.com", "content": "Snippet"},
        ]
    }

    with patch("buddy_bot.mcp_server.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client

        result = json.loads(await mod._handle_web_search({"query": "python"}))
        assert len(result) == 1
        assert result[0]["title"] == "Result 1"


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
    """list_tools() returns all 13 tools."""
    from buddy_bot.mcp_server import list_tools
    tools = await list_tools()
    assert len(tools) == 13
