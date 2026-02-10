"""Google Calendar tool handlers."""

import json
import logging
from datetime import datetime, timedelta, timezone

from buddy_bot.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

CALENDAR_LIST_EVENTS_SCHEMA = {
    "type": "object",
    "properties": {
        "days_ahead": {
            "type": "integer",
            "description": "Number of days to look ahead",
            "default": 7,
        },
        "max_results": {"type": "integer", "default": 10},
    },
}

CALENDAR_CREATE_EVENT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "Event title"},
        "start_time": {"type": "string", "description": "ISO 8601 start time"},
        "end_time": {"type": "string", "description": "ISO 8601 end time"},
        "description": {"type": "string", "description": "Event description"},
        "location": {"type": "string", "description": "Event location"},
    },
    "required": ["summary", "start_time", "end_time"],
}

CALENDAR_DELETE_EVENT_SCHEMA = {
    "type": "object",
    "properties": {
        "event_id": {
            "type": "string",
            "description": "The calendar event ID to delete",
        },
    },
    "required": ["event_id"],
}


def _build_service(credentials):
    """Build a Google Calendar API service."""
    from googleapiclient.discovery import build

    return build("calendar", "v3", credentials=credentials)


def register_calendar_tools(
    registry: ToolRegistry,
    get_credentials,
) -> None:
    """Register Google Calendar tools with the registry.

    Args:
        registry: The tool registry to register with.
        get_credentials: Async callable returning Google OAuth credentials.
    """

    async def handle_calendar_list_events(input: dict) -> str:
        days_ahead = input.get("days_ahead", 7)
        max_results = input.get("max_results", 10)

        creds = await get_credentials()
        service = _build_service(creds)

        now = datetime.now(timezone.utc)
        time_min = now.isoformat()
        time_max = (now + timedelta(days=days_ahead)).isoformat()

        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        events = []
        for item in result.get("items", []):
            events.append(
                {
                    "event_id": item.get("id"),
                    "summary": item.get("summary", "(no title)"),
                    "start": item.get("start", {}).get("dateTime", item.get("start", {}).get("date")),
                    "end": item.get("end", {}).get("dateTime", item.get("end", {}).get("date")),
                    "location": item.get("location", ""),
                }
            )
        return json.dumps(events)

    async def handle_calendar_create_event(input: dict) -> str:
        creds = await get_credentials()
        service = _build_service(creds)

        event_body = {
            "summary": input["summary"],
            "start": {"dateTime": input["start_time"]},
            "end": {"dateTime": input["end_time"]},
        }
        if input.get("description"):
            event_body["description"] = input["description"]
        if input.get("location"):
            event_body["location"] = input["location"]

        created = service.events().insert(calendarId="primary", body=event_body).execute()
        return json.dumps(
            {
                "status": "created",
                "event_id": created.get("id"),
                "link": created.get("htmlLink", ""),
            }
        )

    async def handle_calendar_delete_event(input: dict) -> str:
        creds = await get_credentials()
        service = _build_service(creds)

        service.events().delete(calendarId="primary", eventId=input["event_id"]).execute()
        return json.dumps({"status": "deleted", "event_id": input["event_id"]})

    registry.register(
        "calendar_list_events",
        "List upcoming events from the user's Google Calendar.",
        CALENDAR_LIST_EVENTS_SCHEMA,
        handle_calendar_list_events,
    )
    registry.register(
        "calendar_create_event",
        "Create a new event on the user's Google Calendar.",
        CALENDAR_CREATE_EVENT_SCHEMA,
        handle_calendar_create_event,
    )
    registry.register(
        "calendar_delete_event",
        "Delete an event from the user's Google Calendar.",
        CALENDAR_DELETE_EVENT_SCHEMA,
        handle_calendar_delete_event,
    )
