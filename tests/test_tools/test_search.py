"""Tests for buddy_bot.tools.search module."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from buddy_bot.tools.registry import ToolRegistry
from buddy_bot.tools.search import register_search_tool


async def test_search_no_api_key():
    registry = ToolRegistry()
    register_search_tool(registry, api_key="")
    result = await registry.dispatch("web_search", {"query": "test"})
    parsed = json.loads(result)
    assert "error" in parsed
    assert "not configured" in parsed["error"]


async def test_search_with_mocked_api():
    registry = ToolRegistry()
    register_search_tool(registry, api_key="tvly-test")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "results": [
            {"title": "Result 1", "url": "https://example.com", "content": "Snippet text"},
        ]
    }

    with patch("buddy_bot.tools.search.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client

        result = await registry.dispatch("web_search", {"query": "python asyncio"})
        parsed = json.loads(result)
        assert len(parsed) == 1
        assert parsed[0]["title"] == "Result 1"
        assert parsed[0]["url"] == "https://example.com"


async def test_search_api_error():
    registry = ToolRegistry()
    register_search_tool(registry, api_key="tvly-test")

    with patch("buddy_bot.tools.search.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("timeout")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client

        result = await registry.dispatch("web_search", {"query": "test"})
        parsed = json.loads(result)
        assert "error" in parsed
