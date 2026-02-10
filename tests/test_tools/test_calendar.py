"""Tests for buddy_bot.tools.calendar module."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from buddy_bot.tools.calendar import register_calendar_tools
from buddy_bot.tools.registry import ToolRegistry


@pytest.fixture
def setup():
    registry = ToolRegistry()
    mock_creds = AsyncMock(return_value=MagicMock())
    register_calendar_tools(registry, mock_creds)
    return registry, mock_creds


@patch("buddy_bot.tools.calendar._build_service")
async def test_list_events(mock_build, setup):
    registry, _ = setup
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.events.return_value.list.return_value.execute.return_value = {
        "items": [
            {
                "id": "ev1",
                "summary": "Meeting",
                "start": {"dateTime": "2026-02-10T10:00:00Z"},
                "end": {"dateTime": "2026-02-10T11:00:00Z"},
                "location": "Office",
            }
        ]
    }
    result = await registry.dispatch("calendar_list_events", {"days_ahead": 7})
    events = json.loads(result)
    assert len(events) == 1
    assert events[0]["summary"] == "Meeting"
    assert events[0]["event_id"] == "ev1"


@patch("buddy_bot.tools.calendar._build_service")
async def test_create_event(mock_build, setup):
    registry, _ = setup
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.events.return_value.insert.return_value.execute.return_value = {
        "id": "new_ev",
        "htmlLink": "https://calendar.google.com/event/new_ev",
    }
    result = await registry.dispatch(
        "calendar_create_event",
        {
            "summary": "Lunch",
            "start_time": "2026-02-11T12:00:00Z",
            "end_time": "2026-02-11T13:00:00Z",
        },
    )
    parsed = json.loads(result)
    assert parsed["status"] == "created"
    assert parsed["event_id"] == "new_ev"


@patch("buddy_bot.tools.calendar._build_service")
async def test_delete_event(mock_build, setup):
    registry, _ = setup
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.events.return_value.delete.return_value.execute.return_value = None
    result = await registry.dispatch("calendar_delete_event", {"event_id": "ev_to_delete"})
    parsed = json.loads(result)
    assert parsed["status"] == "deleted"
    assert parsed["event_id"] == "ev_to_delete"


@patch("buddy_bot.tools.calendar._build_service")
async def test_list_events_default_values(mock_build, setup):
    registry, _ = setup
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.events.return_value.list.return_value.execute.return_value = {"items": []}
    await registry.dispatch("calendar_list_events", {})
    call_kwargs = mock_service.events.return_value.list.call_args
    assert call_kwargs[1]["maxResults"] == 10


async def test_all_calendar_tools_registered(setup):
    registry, _ = setup
    defs = {d["name"] for d in registry.get_tool_definitions()}
    assert "calendar_list_events" in defs
    assert "calendar_create_event" in defs
    assert "calendar_delete_event" in defs
