"""Tests for buddy_bot.tools.memory module."""

import json
from unittest.mock import AsyncMock

import pytest

from buddy_bot.tools.memory import register_memory_tools
from buddy_bot.tools.registry import ToolRegistry


@pytest.fixture
def setup():
    registry = ToolRegistry()
    client = AsyncMock()
    register_memory_tools(registry, client)
    return registry, client


async def test_get_episodes_calls_client(setup):
    registry, client = setup
    client.get_episodes.return_value = [{"name": "ep1"}]
    result = await registry.dispatch("get_episodes", {"group_ids": ["main"], "max_episodes": 3})
    client.get_episodes.assert_called_once_with(["main"], 3)
    parsed = json.loads(result)
    assert parsed == [{"name": "ep1"}]


async def test_get_episodes_default_args(setup):
    registry, client = setup
    client.get_episodes.return_value = []
    await registry.dispatch("get_episodes", {})
    client.get_episodes.assert_called_once_with(["main"], 5)


async def test_search_memory_facts(setup):
    registry, client = setup
    client.search_facts.return_value = [{"fact": "test"}]
    result = await registry.dispatch("search_memory_facts", {"query": "pending items"})
    client.search_facts.assert_called_once_with("pending items", ["main"])
    parsed = json.loads(result)
    assert parsed == [{"fact": "test"}]


async def test_search_nodes(setup):
    registry, client = setup
    client.search_nodes.return_value = [{"node": "user"}]
    result = await registry.dispatch("search_nodes", {"query": "project X"})
    client.search_nodes.assert_called_once_with("project X", ["main"])
    parsed = json.loads(result)
    assert parsed == [{"node": "user"}]


async def test_add_memory(setup):
    registry, client = setup
    client.add_memory.return_value = {"ok": True}
    result = await registry.dispatch(
        "add_memory", {"name": "summary", "episode_body": "User asked X"}
    )
    client.add_memory.assert_called_once_with("summary", "User asked X", "main", "text")
    parsed = json.loads(result)
    assert parsed["ok"] is True


async def test_client_error_returns_graceful(setup):
    registry, client = setup
    client.get_episodes.side_effect = RuntimeError("connection failed")
    result = await registry.dispatch("get_episodes", {})
    parsed = json.loads(result)
    assert "error" in parsed


async def test_all_four_tools_registered(setup):
    registry, _ = setup
    defs = registry.get_tool_definitions()
    names = {d["name"] for d in defs}
    assert names == {"get_episodes", "search_memory_facts", "search_nodes", "add_memory"}


async def test_schemas_match_spec(setup):
    registry, _ = setup
    defs = {d["name"]: d for d in registry.get_tool_definitions()}

    # get_episodes has no required fields
    assert defs["get_episodes"]["input_schema"]["required"] == []

    # search_memory_facts requires query
    assert "query" in defs["search_memory_facts"]["input_schema"]["required"]

    # search_nodes requires query
    assert "query" in defs["search_nodes"]["input_schema"]["required"]

    # add_memory requires name and episode_body
    assert set(defs["add_memory"]["input_schema"]["required"]) == {"name", "episode_body"}
