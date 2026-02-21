"""MCP stdio server exposing buddy-bot tools to Claude Code CLI.

Run as: python -m buddy_bot.mcp_server
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from urllib.error import URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------
USER_TIMEZONE = os.environ.get("USER_TIMEZONE", "UTC")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")

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
    Tool(
        name="notify_progress",
        description=(
            "Send a short progress message to the user's Telegram chat. "
            "Use this to acknowledge receipt or signal progress during long operations. "
            "Keep messages short (a few words). Don't overuse — 1-2 per interaction."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "chat_id": {
                    "type": "string",
                    "description": "The user's chat_id (provided in your prompt context).",
                },
                "message": {
                    "type": "string",
                    "description": "Short progress message, e.g. 'On it!' or 'Almost done!'",
                },
            },
            "required": ["chat_id", "message"],
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


async def _handle_notify_progress(arguments: dict) -> str:
    """Send a progress message to the user via Telegram Bot API."""
    chat_id = arguments.get("chat_id", "")
    message = arguments.get("message", "")

    if not chat_id or not message:
        return json.dumps({"error": "chat_id and message are required"})

    token = TELEGRAM_TOKEN
    if not token:
        return json.dumps({"error": "TELEGRAM_TOKEN not configured"})

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": message}).encode()
    req = Request(url, data=payload, headers={"Content-Type": "application/json"})

    try:
        with urlopen(req, timeout=10) as resp:
            resp.read()
        return json.dumps({"status": "sent"})
    except (URLError, OSError) as exc:
        logger.warning("notify_progress failed for chat %s: %s", chat_id, exc)
        return json.dumps({"error": f"Failed to send: {exc}"})


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------
HANDLERS: dict[str, object] = {
    "get_current_time": _handle_get_current_time,
    "notify_progress": _handle_notify_progress,
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
