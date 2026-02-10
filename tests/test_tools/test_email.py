"""Tests for buddy_bot.tools.email module."""

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from buddy_bot.tools.email import _decode_body, _get_header, register_email_tools
from buddy_bot.tools.registry import ToolRegistry


@pytest.fixture
def setup():
    registry = ToolRegistry()
    mock_creds = AsyncMock(return_value=MagicMock())
    register_email_tools(registry, mock_creds)
    return registry, mock_creds


def test_get_header():
    headers = [
        {"name": "Subject", "value": "Test Subject"},
        {"name": "From", "value": "test@example.com"},
    ]
    assert _get_header(headers, "Subject") == "Test Subject"
    assert _get_header(headers, "from") == "test@example.com"
    assert _get_header(headers, "Missing") == ""


def test_decode_body_plain_text():
    data = base64.urlsafe_b64encode(b"Hello world").decode()
    payload = {"mimeType": "text/plain", "body": {"data": data}}
    assert _decode_body(payload) == "Hello world"


def test_decode_body_multipart():
    data = base64.urlsafe_b64encode(b"Body text").decode()
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/plain", "body": {"data": data}},
            {"mimeType": "text/html", "body": {"data": base64.urlsafe_b64encode(b"<p>html</p>").decode()}},
        ],
    }
    assert _decode_body(payload) == "Body text"


def test_decode_body_no_body():
    payload = {"mimeType": "multipart/mixed", "parts": []}
    assert _decode_body(payload) == "(no body)"


@patch("buddy_bot.tools.email._build_service")
async def test_list_messages(mock_build, setup):
    registry, _ = setup
    mock_service = MagicMock()
    mock_build.return_value = mock_service

    mock_service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": [{"id": "msg1"}]
    }
    mock_service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
        "id": "msg1",
        "snippet": "Preview text",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Test"},
                {"name": "From", "value": "alice@example.com"},
                {"name": "Date", "value": "Mon, 10 Feb 2026"},
            ]
        },
    }

    result = await registry.dispatch("email_list_messages", {"query": "is:unread"})
    messages = json.loads(result)
    assert len(messages) == 1
    assert messages[0]["subject"] == "Test"
    assert messages[0]["from"] == "alice@example.com"


@patch("buddy_bot.tools.email._build_service")
async def test_read_message(mock_build, setup):
    registry, _ = setup
    mock_service = MagicMock()
    mock_build.return_value = mock_service

    body_data = base64.urlsafe_b64encode(b"Hello from the email").decode()
    mock_service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
        "id": "msg1",
        "payload": {
            "mimeType": "text/plain",
            "body": {"data": body_data},
            "headers": [
                {"name": "From", "value": "alice@example.com"},
                {"name": "To", "value": "me@example.com"},
                {"name": "Subject", "value": "Test"},
                {"name": "Date", "value": "Mon, 10 Feb 2026"},
            ],
        },
    }

    result = await registry.dispatch("email_read_message", {"message_id": "msg1"})
    parsed = json.loads(result)
    assert parsed["body"] == "Hello from the email"
    assert parsed["from"] == "alice@example.com"


@patch("buddy_bot.tools.email._build_service")
async def test_send_message(mock_build, setup):
    registry, _ = setup
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.users.return_value.messages.return_value.send.return_value.execute.return_value = {
        "id": "sent_msg_1"
    }

    result = await registry.dispatch(
        "email_send_message",
        {"to": "bob@example.com", "subject": "Hi", "body": "Hello Bob"},
    )
    parsed = json.loads(result)
    assert parsed["status"] == "sent"
    assert parsed["message_id"] == "sent_msg_1"


async def test_all_email_tools_registered(setup):
    registry, _ = setup
    defs = {d["name"] for d in registry.get_tool_definitions()}
    assert "email_list_messages" in defs
    assert "email_read_message" in defs
    assert "email_send_message" in defs
