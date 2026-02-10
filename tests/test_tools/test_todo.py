"""Tests for buddy_bot.tools.todo module."""

import json

import pytest

from buddy_bot.todo import TodoStore
from buddy_bot.tools.registry import ToolRegistry
from buddy_bot.tools.todo import register_todo_tools


@pytest.fixture
def setup(tmp_path):
    store = TodoStore(str(tmp_path / "test.db"))
    registry = ToolRegistry()
    chat_id_ref = {"chat_id": "123"}
    register_todo_tools(registry, store, chat_id_ref)
    yield registry, store, chat_id_ref
    store.close()


async def test_todo_add_via_dispatch(setup):
    registry, store, _ = setup
    result = await registry.dispatch("todo_add", {"title": "Test task", "priority": "high"})
    parsed = json.loads(result)
    assert parsed["status"] == "created"
    assert parsed["title"] == "Test task"
    assert parsed["priority"] == "high"
    assert "todo_id" in parsed


async def test_todo_list_via_dispatch(setup):
    registry, store, _ = setup
    await registry.dispatch("todo_add", {"title": "Task A"})
    await registry.dispatch("todo_add", {"title": "Task B"})

    result = await registry.dispatch("todo_list", {})
    parsed = json.loads(result)
    assert len(parsed) == 2


async def test_todo_complete_via_dispatch(setup):
    registry, store, _ = setup
    add_result = json.loads(await registry.dispatch("todo_add", {"title": "To complete"}))
    todo_id = add_result["todo_id"]

    result = await registry.dispatch("todo_complete", {"todo_id": todo_id})
    parsed = json.loads(result)
    assert parsed["status"] == "completed"


async def test_todo_delete_via_dispatch(setup):
    registry, store, _ = setup
    add_result = json.loads(await registry.dispatch("todo_add", {"title": "To delete"}))
    todo_id = add_result["todo_id"]

    result = await registry.dispatch("todo_delete", {"todo_id": todo_id})
    parsed = json.loads(result)
    assert parsed["status"] == "deleted"

    # Verify it's gone
    list_result = json.loads(await registry.dispatch("todo_list", {}))
    assert len(list_result) == 0


async def test_todo_complete_nonexistent(setup):
    registry, _, _ = setup
    result = await registry.dispatch("todo_complete", {"todo_id": 999})
    parsed = json.loads(result)
    assert "error" in parsed


async def test_all_todo_tools_registered(setup):
    registry, _, _ = setup
    defs = registry.get_tool_definitions()
    names = {d["name"] for d in defs}
    assert {"todo_add", "todo_list", "todo_complete", "todo_delete"} <= names


async def test_chat_id_ref_respected(setup):
    registry, store, chat_id_ref = setup

    chat_id_ref["chat_id"] = "aaa"
    await registry.dispatch("todo_add", {"title": "For AAA"})

    chat_id_ref["chat_id"] = "bbb"
    await registry.dispatch("todo_add", {"title": "For BBB"})

    chat_id_ref["chat_id"] = "aaa"
    result = json.loads(await registry.dispatch("todo_list", {}))
    assert len(result) == 1
    assert result[0]["title"] == "For AAA"
