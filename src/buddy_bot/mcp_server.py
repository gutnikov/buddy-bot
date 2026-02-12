"""MCP stdio server exposing buddy-bot tools to Claude Code CLI.

Run as: python -m buddy_bot.mcp_server
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from buddy_bot.todo import TodoStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------
HISTORY_DB = os.environ.get("HISTORY_DB", "/data/history.db")
USER_TIMEZONE = os.environ.get("USER_TIMEZONE", "UTC")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY", "")
GOOGLE_CREDENTIALS_PATH = os.environ.get(
    "GOOGLE_CREDENTIALS_PATH", "/app/credentials/client_secret.json"
)

# ---------------------------------------------------------------------------
# Lazy-initialized singletons
# ---------------------------------------------------------------------------
_todo_store: TodoStore | None = None
_google_auth = None


def _get_todo_store() -> TodoStore:
    global _todo_store
    if _todo_store is None:
        _todo_store = TodoStore(HISTORY_DB)
    return _todo_store


def _get_google_auth():
    global _google_auth
    if _google_auth is None:
        from buddy_bot.tools.google_auth import GoogleAuth
        _google_auth = GoogleAuth(GOOGLE_CREDENTIALS_PATH, HISTORY_DB)
    return _google_auth


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------
TOOLS = [
    Tool(
        name="todo_add",
        description="Add a new task to the user's todo list.",
        inputSchema={
            "type": "object",
            "properties": {
                "chat_id": {"type": "string", "description": "The chat ID for the user"},
                "title": {"type": "string", "description": "Task title or description"},
                "due_date": {"type": "string", "description": "Due date in YYYY-MM-DD format (optional)"},
                "priority": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "Task priority",
                    "default": "medium",
                },
            },
            "required": ["chat_id", "title"],
        },
    ),
    Tool(
        name="todo_list",
        description="List tasks from the user's todo list. Can filter by status and due date.",
        inputSchema={
            "type": "object",
            "properties": {
                "chat_id": {"type": "string", "description": "The chat ID for the user"},
                "status": {
                    "type": "string",
                    "enum": ["pending", "done"],
                    "description": "Filter by status. Omit to show all.",
                },
                "days_ahead": {
                    "type": "integer",
                    "description": "Only show tasks due within this many days",
                },
            },
            "required": ["chat_id"],
        },
    ),
    Tool(
        name="todo_complete",
        description="Mark a task as completed on the user's todo list.",
        inputSchema={
            "type": "object",
            "properties": {
                "chat_id": {"type": "string", "description": "The chat ID for the user"},
                "todo_id": {"type": "integer", "description": "The task ID to mark as done"},
            },
            "required": ["chat_id", "todo_id"],
        },
    ),
    Tool(
        name="todo_delete",
        description="Delete a task from the user's todo list.",
        inputSchema={
            "type": "object",
            "properties": {
                "chat_id": {"type": "string", "description": "The chat ID for the user"},
                "todo_id": {"type": "integer", "description": "The task ID to delete"},
            },
            "required": ["chat_id", "todo_id"],
        },
    ),
    Tool(
        name="calendar_list_events",
        description="List upcoming events from the user's Google Calendar.",
        inputSchema={
            "type": "object",
            "properties": {
                "days_ahead": {"type": "integer", "description": "Number of days to look ahead", "default": 7},
                "max_results": {"type": "integer", "default": 10},
            },
        },
    ),
    Tool(
        name="calendar_create_event",
        description="Create a new event on the user's Google Calendar.",
        inputSchema={
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Event title"},
                "start_time": {"type": "string", "description": "ISO 8601 start time"},
                "end_time": {"type": "string", "description": "ISO 8601 end time"},
                "description": {"type": "string", "description": "Event description"},
                "location": {"type": "string", "description": "Event location"},
            },
            "required": ["summary", "start_time", "end_time"],
        },
    ),
    Tool(
        name="calendar_delete_event",
        description="Delete an event from the user's Google Calendar.",
        inputSchema={
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The calendar event ID to delete"},
            },
            "required": ["event_id"],
        },
    ),
    Tool(
        name="email_list_messages",
        description="List recent emails from the user's inbox.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Gmail search query (e.g., 'is:unread', 'from:boss@company.com')",
                    "default": "is:unread",
                },
                "max_results": {"type": "integer", "default": 10},
            },
        },
    ),
    Tool(
        name="email_read_message",
        description="Read the full content of a specific email.",
        inputSchema={
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "Gmail message ID"},
            },
            "required": ["message_id"],
        },
    ),
    Tool(
        name="email_send_message",
        description="Send an email on behalf of the user. Always confirm with the user before sending.",
        inputSchema={
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string"},
                "body": {"type": "string", "description": "Email body (plain text)"},
                "reply_to_message_id": {
                    "type": "string",
                    "description": "Message ID to reply to (optional)",
                },
            },
            "required": ["to", "subject", "body"],
        },
    ),
    Tool(
        name="web_search",
        description="Search the web for current information.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="perplexity_search",
        description="Search the web using Perplexity AI for synthesized answers with citations. Best for questions needing research and analysis.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query — works best with natural language questions",
                },
            },
            "required": ["query"],
        },
    ),
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


async def _handle_todo_add(arguments: dict) -> str:
    store = _get_todo_store()
    chat_id = arguments["chat_id"]
    title = arguments["title"]
    due_date = arguments.get("due_date")
    priority = arguments.get("priority", "medium")
    item = await store.add(chat_id, title, due_date, priority)
    return json.dumps({
        "status": "created",
        "todo_id": item.id,
        "title": item.title,
        "due_date": item.due_date,
        "priority": item.priority,
    })


async def _handle_todo_list(arguments: dict) -> str:
    store = _get_todo_store()
    chat_id = arguments["chat_id"]
    status = arguments.get("status")
    days_ahead = arguments.get("days_ahead")
    items = await store.list(chat_id, status, days_ahead)
    return json.dumps([
        {
            "todo_id": item.id,
            "title": item.title,
            "due_date": item.due_date,
            "priority": item.priority,
            "status": item.status,
            "created_at": item.created_at,
            "completed_at": item.completed_at,
        }
        for item in items
    ])


async def _handle_todo_complete(arguments: dict) -> str:
    store = _get_todo_store()
    chat_id = arguments["chat_id"]
    todo_id = arguments["todo_id"]
    item = await store.complete(chat_id, todo_id)
    if item is None:
        return json.dumps({"error": f"Todo #{todo_id} not found"})
    return json.dumps({
        "status": "completed",
        "todo_id": item.id,
        "title": item.title,
    })


async def _handle_todo_delete(arguments: dict) -> str:
    store = _get_todo_store()
    chat_id = arguments["chat_id"]
    todo_id = arguments["todo_id"]
    deleted = await store.delete(chat_id, todo_id)
    if not deleted:
        return json.dumps({"error": f"Todo #{todo_id} not found"})
    return json.dumps({"status": "deleted", "todo_id": todo_id})


def _build_google_service(service_name: str, version: str, scopes: list[str]):
    """Build a Google API service synchronously."""
    auth = _get_google_auth()
    # GoogleAuth.get_credentials is async, but MCP handlers are async too
    # We'll use the sync internal method directly since we're in a subprocess
    creds = auth._get_credentials_sync(service_name, scopes)
    from googleapiclient.discovery import build
    return build(service_name, version, credentials=creds)


async def _handle_calendar_list_events(arguments: dict) -> str:
    days_ahead = arguments.get("days_ahead", 7)
    max_results = arguments.get("max_results", 10)

    service = await asyncio.to_thread(
        _build_google_service,
        "calendar", "v3",
        ["https://www.googleapis.com/auth/calendar"],
    )

    now = datetime.now(timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=days_ahead)).isoformat()

    result = await asyncio.to_thread(
        lambda: service.events()
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
        events.append({
            "event_id": item.get("id"),
            "summary": item.get("summary", "(no title)"),
            "start": item.get("start", {}).get("dateTime", item.get("start", {}).get("date")),
            "end": item.get("end", {}).get("dateTime", item.get("end", {}).get("date")),
            "location": item.get("location", ""),
        })
    return json.dumps(events)


async def _handle_calendar_create_event(arguments: dict) -> str:
    service = await asyncio.to_thread(
        _build_google_service,
        "calendar", "v3",
        ["https://www.googleapis.com/auth/calendar"],
    )

    event_body = {
        "summary": arguments["summary"],
        "start": {"dateTime": arguments["start_time"]},
        "end": {"dateTime": arguments["end_time"]},
    }
    if arguments.get("description"):
        event_body["description"] = arguments["description"]
    if arguments.get("location"):
        event_body["location"] = arguments["location"]

    created = await asyncio.to_thread(
        lambda: service.events().insert(calendarId="primary", body=event_body).execute()
    )
    return json.dumps({
        "status": "created",
        "event_id": created.get("id"),
        "link": created.get("htmlLink", ""),
    })


async def _handle_calendar_delete_event(arguments: dict) -> str:
    service = await asyncio.to_thread(
        _build_google_service,
        "calendar", "v3",
        ["https://www.googleapis.com/auth/calendar"],
    )
    await asyncio.to_thread(
        lambda: service.events().delete(
            calendarId="primary", eventId=arguments["event_id"]
        ).execute()
    )
    return json.dumps({"status": "deleted", "event_id": arguments["event_id"]})


def _get_email_header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


async def _handle_email_list_messages(arguments: dict) -> str:
    import base64
    query = arguments.get("query", "is:unread")
    max_results = arguments.get("max_results", 10)

    service = await asyncio.to_thread(
        _build_google_service,
        "gmail", "v1",
        ["https://www.googleapis.com/auth/gmail.modify"],
    )

    result = await asyncio.to_thread(
        lambda: service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )

    messages = []
    for msg_ref in result.get("messages", []):
        msg = await asyncio.to_thread(
            lambda mid=msg_ref["id"]: service.users()
            .messages()
            .get(userId="me", id=mid, format="metadata", metadataHeaders=["From", "Subject", "Date"])
            .execute()
        )
        headers = msg.get("payload", {}).get("headers", [])
        messages.append({
            "message_id": msg["id"],
            "subject": _get_email_header(headers, "Subject"),
            "from": _get_email_header(headers, "From"),
            "date": _get_email_header(headers, "Date"),
            "snippet": msg.get("snippet", ""),
        })
    return json.dumps(messages)


async def _handle_email_read_message(arguments: dict) -> str:
    import base64
    service = await asyncio.to_thread(
        _build_google_service,
        "gmail", "v1",
        ["https://www.googleapis.com/auth/gmail.modify"],
    )

    msg = await asyncio.to_thread(
        lambda: service.users()
        .messages()
        .get(userId="me", id=arguments["message_id"], format="full")
        .execute()
    )

    headers = msg.get("payload", {}).get("headers", [])
    body = _decode_email_body(msg.get("payload", {}))

    return json.dumps({
        "message_id": msg["id"],
        "from": _get_email_header(headers, "From"),
        "to": _get_email_header(headers, "To"),
        "subject": _get_email_header(headers, "Subject"),
        "date": _get_email_header(headers, "Date"),
        "body": body,
    })


def _decode_email_body(payload: dict) -> str:
    """Decode email body from MIME payload."""
    import base64

    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")

    for part in payload.get("parts", []):
        if part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")

    return "(no body)"


async def _handle_email_send_message(arguments: dict) -> str:
    import base64
    from email.mime.text import MIMEText

    service = await asyncio.to_thread(
        _build_google_service,
        "gmail", "v1",
        ["https://www.googleapis.com/auth/gmail.modify"],
    )

    message = MIMEText(arguments["body"])
    message["to"] = arguments["to"]
    message["subject"] = arguments["subject"]

    body = {}
    if arguments.get("reply_to_message_id"):
        original = await asyncio.to_thread(
            lambda: service.users()
            .messages()
            .get(
                userId="me",
                id=arguments["reply_to_message_id"],
                format="metadata",
                metadataHeaders=["Message-ID", "Subject"],
            )
            .execute()
        )
        orig_headers = original.get("payload", {}).get("headers", [])
        message_id = _get_email_header(orig_headers, "Message-ID")
        if message_id:
            message["In-Reply-To"] = message_id
            message["References"] = message_id
        body["threadId"] = original.get("threadId", "")

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    body["raw"] = raw

    sent = await asyncio.to_thread(
        lambda: service.users().messages().send(userId="me", body=body).execute()
    )
    return json.dumps({"status": "sent", "message_id": sent.get("id", "")})


async def _handle_web_search(arguments: dict) -> str:
    if not TAVILY_API_KEY:
        return json.dumps({"error": "Web search is not configured. Set TAVILY_API_KEY."})

    query = arguments["query"]
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": TAVILY_API_KEY, "query": query, "max_results": 5},
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", "")[:300],
            })
        return json.dumps(results)
    except Exception as e:
        logger.warning("Web search failed: %s", e)
        return json.dumps({"error": f"Web search failed: {e}"})


async def _handle_perplexity_search(arguments: dict) -> str:
    if not PERPLEXITY_API_KEY:
        return json.dumps({"error": "Perplexity search is not configured. Set PERPLEXITY_API_KEY."})

    query = arguments["query"]
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "sonar",
                    "messages": [{"role": "user", "content": query}],
                },
            )
            resp.raise_for_status()
            data = resp.json()

        choice = data.get("choices", [{}])[0]
        answer = choice.get("message", {}).get("content", "")
        citations = data.get("citations", [])

        result = {"answer": answer}
        if citations:
            result["citations"] = citations
        return json.dumps(result)
    except Exception as e:
        logger.warning("Perplexity search failed: %s", e)
        return json.dumps({"error": f"Perplexity search failed: {e}"})


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
    "todo_add": _handle_todo_add,
    "todo_list": _handle_todo_list,
    "todo_complete": _handle_todo_complete,
    "todo_delete": _handle_todo_delete,
    "calendar_list_events": _handle_calendar_list_events,
    "calendar_create_event": _handle_calendar_create_event,
    "calendar_delete_event": _handle_calendar_delete_event,
    "email_list_messages": _handle_email_list_messages,
    "email_read_message": _handle_email_read_message,
    "email_send_message": _handle_email_send_message,
    "web_search": _handle_web_search,
    "perplexity_search": _handle_perplexity_search,
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
