"""MCP stdio server exposing buddy-bot tools to Claude Code CLI.

Run as: python -m buddy_bot.mcp_server
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------
USER_TIMEZONE = os.environ.get("USER_TIMEZONE", "UTC")

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------
TOOLS = [
    Tool(
        name="get_current_time",
        description="Get the current date and time in the user's timezone.",
        inputSchema={
            "type": "object",
            "properties": {
                "timezone": {"type": "string", "default": "UTC"},
            },
        },
    ),
]

# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


async def _handle_get_current_time(arguments: dict) -> str:
    tz_name = arguments.get("timezone") or USER_TIMEZONE
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, KeyError):
        return json.dumps({"error": f"Unknown timezone: {tz_name}"})

    now = datetime.now(tz)
    return json.dumps({
        "datetime": now.isoformat(),
        "date": now.strftime("%A, %B %d, %Y"),
        "time": now.strftime("%I:%M %p"),
        "timezone": tz_name,
    })


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------
HANDLERS: dict[str, object] = {
    "get_current_time": _handle_get_current_time,
}

# ---------------------------------------------------------------------------
# MCP server setup
# ---------------------------------------------------------------------------
server = Server("buddy-bot-tools")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    handler = HANDLERS.get(name)
    if handler is None:
        return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    try:
        result = await handler(arguments)
        return [TextContent(type="text", text=result)]
    except Exception as e:
        logger.exception("Tool %s failed", name)
        return [TextContent(type="text", text=json.dumps({"error": f"Tool {name} failed: {e}"}))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    asyncio.run(main())
