"""Current time tool handler."""

import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from buddy_bot.tools.registry import ToolRegistry

GET_CURRENT_TIME_SCHEMA = {
    "type": "object",
    "properties": {
        "timezone": {"type": "string", "default": "UTC"},
    },
}


def register_time_tool(registry: ToolRegistry, default_timezone: str = "UTC") -> None:
    async def handle_get_current_time(input: dict) -> str:
        tz_name = input.get("timezone") or default_timezone
        try:
            tz = ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, KeyError):
            return json.dumps({"error": f"Unknown timezone: {tz_name}"})

        now = datetime.now(tz)
        return json.dumps(
            {
                "datetime": now.isoformat(),
                "date": now.strftime("%A, %B %d, %Y"),
                "time": now.strftime("%I:%M %p"),
                "timezone": tz_name,
            }
        )

    registry.register(
        "get_current_time",
        "Get the current date and time in the user's timezone.",
        GET_CURRENT_TIME_SCHEMA,
        handle_get_current_time,
    )
