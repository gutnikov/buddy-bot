"""Tests for buddy_bot.tools.time module."""

import json

import pytest

from buddy_bot.tools.registry import ToolRegistry
from buddy_bot.tools.time import register_time_tool


@pytest.fixture
def registry():
    r = ToolRegistry()
    register_time_tool(r, default_timezone="UTC")
    return r


async def test_get_current_time_utc(registry):
    result = await registry.dispatch("get_current_time", {"timezone": "UTC"})
    parsed = json.loads(result)
    assert "datetime" in parsed
    assert parsed["timezone"] == "UTC"


async def test_get_current_time_nondefault_tz(registry):
    result = await registry.dispatch("get_current_time", {"timezone": "America/New_York"})
    parsed = json.loads(result)
    assert parsed["timezone"] == "America/New_York"
    assert "datetime" in parsed


async def test_get_current_time_invalid_tz(registry):
    result = await registry.dispatch("get_current_time", {"timezone": "Invalid/Zone"})
    parsed = json.loads(result)
    assert "error" in parsed
    assert "Unknown timezone" in parsed["error"]


async def test_get_current_time_uses_default():
    r = ToolRegistry()
    register_time_tool(r, default_timezone="Europe/London")
    result = await r.dispatch("get_current_time", {})
    parsed = json.loads(result)
    assert parsed["timezone"] == "Europe/London"


async def test_get_current_time_has_date_and_time(registry):
    result = await registry.dispatch("get_current_time", {})
    parsed = json.loads(result)
    assert "date" in parsed
    assert "time" in parsed
