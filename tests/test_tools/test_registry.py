"""Tests for buddy_bot.tools.registry module."""

import json

import pytest

from buddy_bot.tools.registry import ToolRegistry


async def _echo_handler(input):
    return {"echo": input}


async def _failing_handler(input):
    raise RuntimeError("boom")


@pytest.fixture
def registry():
    r = ToolRegistry()
    r.register(
        name="echo",
        description="Echoes input",
        input_schema={"type": "object", "properties": {"msg": {"type": "string"}}},
        handler=_echo_handler,
    )
    return r


async def test_register_and_get_definitions(registry):
    defs = registry.get_tool_definitions()
    assert len(defs) == 1
    assert defs[0]["name"] == "echo"
    assert defs[0]["description"] == "Echoes input"
    assert "properties" in defs[0]["input_schema"]


async def test_dispatch_calls_handler(registry):
    result = await registry.dispatch("echo", {"msg": "hello"})
    parsed = json.loads(result)
    assert parsed["echo"]["msg"] == "hello"


async def test_dispatch_unknown_tool(registry):
    result = await registry.dispatch("nonexistent", {})
    parsed = json.loads(result)
    assert "error" in parsed
    assert "Unknown tool" in parsed["error"]


async def test_dispatch_handler_exception():
    registry = ToolRegistry()
    registry.register("fail", "Fails", {"type": "object"}, _failing_handler)
    result = await registry.dispatch("fail", {})
    parsed = json.loads(result)
    assert "error" in parsed
    assert "boom" in parsed["error"]


async def test_handler_returning_string():
    async def string_handler(input):
        return "plain string result"

    registry = ToolRegistry()
    registry.register("str_tool", "Returns string", {"type": "object"}, string_handler)
    result = await registry.dispatch("str_tool", {})
    assert result == "plain string result"


async def test_tool_definition_format(registry):
    defs = registry.get_tool_definitions()
    for d in defs:
        assert "name" in d
        assert "description" in d
        assert "input_schema" in d
        assert isinstance(d["input_schema"], dict)
