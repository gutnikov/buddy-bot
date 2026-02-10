"""Gmail tool handlers."""

import base64
import json
import logging
from email.mime.text import MIMEText

from buddy_bot.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

EMAIL_LIST_MESSAGES_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Gmail search query (e.g., 'is:unread', 'from:boss@company.com')",
            "default": "is:unread",
        },
        "max_results": {"type": "integer", "default": 10},
    },
}

EMAIL_READ_MESSAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "message_id": {"type": "string", "description": "Gmail message ID"},
    },
    "required": ["message_id"],
}

EMAIL_SEND_MESSAGE_SCHEMA = {
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
}


def _build_service(credentials):
    """Build a Gmail API service."""
    from googleapiclient.discovery import build

    return build("gmail", "v1", credentials=credentials)


def _get_header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _decode_body(payload: dict) -> str:
    """Decode email body from MIME payload."""
    # Simple text/plain body
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

    # Multipart: look for text/plain part
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")

    # Fallback: try first part with data
    for part in payload.get("parts", []):
        if part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")

    return "(no body)"


def register_email_tools(
    registry: ToolRegistry,
    get_credentials,
) -> None:
    """Register Gmail tools with the registry."""

    async def handle_email_list_messages(input: dict) -> str:
        query = input.get("query", "is:unread")
        max_results = input.get("max_results", 10)

        creds = await get_credentials()
        service = _build_service(creds)

        result = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )

        messages = []
        for msg_ref in result.get("messages", []):
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_ref["id"], format="metadata", metadataHeaders=["From", "Subject", "Date"])
                .execute()
            )
            headers = msg.get("payload", {}).get("headers", [])
            messages.append(
                {
                    "message_id": msg["id"],
                    "subject": _get_header(headers, "Subject"),
                    "from": _get_header(headers, "From"),
                    "date": _get_header(headers, "Date"),
                    "snippet": msg.get("snippet", ""),
                }
            )
        return json.dumps(messages)

    async def handle_email_read_message(input: dict) -> str:
        creds = await get_credentials()
        service = _build_service(creds)

        msg = (
            service.users()
            .messages()
            .get(userId="me", id=input["message_id"], format="full")
            .execute()
        )

        headers = msg.get("payload", {}).get("headers", [])
        body = _decode_body(msg.get("payload", {}))

        return json.dumps(
            {
                "message_id": msg["id"],
                "from": _get_header(headers, "From"),
                "to": _get_header(headers, "To"),
                "subject": _get_header(headers, "Subject"),
                "date": _get_header(headers, "Date"),
                "body": body,
            }
        )

    async def handle_email_send_message(input: dict) -> str:
        creds = await get_credentials()
        service = _build_service(creds)

        message = MIMEText(input["body"])
        message["to"] = input["to"]
        message["subject"] = input["subject"]

        if input.get("reply_to_message_id"):
            # Get original message for threading
            original = (
                service.users()
                .messages()
                .get(userId="me", id=input["reply_to_message_id"], format="metadata", metadataHeaders=["Message-ID", "Subject"])
                .execute()
            )
            orig_headers = original.get("payload", {}).get("headers", [])
            message_id = _get_header(orig_headers, "Message-ID")
            if message_id:
                message["In-Reply-To"] = message_id
                message["References"] = message_id

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        body = {"raw": raw}
        if input.get("reply_to_message_id"):
            body["threadId"] = original.get("threadId", "")

        sent = service.users().messages().send(userId="me", body=body).execute()
        return json.dumps({"status": "sent", "message_id": sent.get("id", "")})

    registry.register(
        "email_list_messages",
        "List recent emails from the user's inbox.",
        EMAIL_LIST_MESSAGES_SCHEMA,
        handle_email_list_messages,
    )
    registry.register(
        "email_read_message",
        "Read the full content of a specific email.",
        EMAIL_READ_MESSAGE_SCHEMA,
        handle_email_read_message,
    )
    registry.register(
        "email_send_message",
        "Send an email on behalf of the user. Always confirm with the user before sending.",
        EMAIL_SEND_MESSAGE_SCHEMA,
        handle_email_send_message,
    )
