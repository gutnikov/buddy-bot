"""Tests for buddy_bot.progress module."""

from buddy_bot.progress import format_tool_progress


def test_known_tool():
    assert format_tool_progress("get_current_time") == "Checking the time..."


def test_unknown_tool():
    assert format_tool_progress("nonexistent_tool") is None


def test_mcp_prefixed_tool():
    assert format_tool_progress("mcp__buddy-bot-tools__get_current_time") == "Checking the time..."


def test_mcp_prefixed_graphiti_tool():
    assert format_tool_progress("mcp__graphiti__search_memory_facts") == "Searching memory..."


def test_all_tools_have_messages():
    """Verify all expected tools are covered."""
    from buddy_bot.progress import TOOL_PROGRESS
    expected_tools = {
        "get_episodes", "search_memory_facts", "search_nodes", "add_memory",
        "get_current_time", "notify_progress",
    }
    assert set(TOOL_PROGRESS.keys()) == expected_tools
