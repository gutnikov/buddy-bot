"""Tests for buddy_bot.tools.perplexity module."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from buddy_bot.tools.perplexity import register_perplexity_tool
from buddy_bot.tools.registry import ToolRegistry


async def test_search_no_api_key():
    registry = ToolRegistry()
    register_perplexity_tool(registry, api_key="")
    result = await registry.dispatch("perplexity_search", {"query": "test"})
    parsed = json.loads(result)
    assert "error" in parsed
    assert "not configured" in parsed["error"]


async def test_search_with_mocked_api():
    registry = ToolRegistry()
    register_perplexity_tool(registry, api_key="pplx-test")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Python asyncio is a library for writing concurrent code."
                }
            }
        ],
        "citations": [
            "https://docs.python.org/3/library/asyncio.html",
            "https://realpython.com/async-io-python/",
        ],
    }

    with patch("buddy_bot.tools.perplexity.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client

        result = await registry.dispatch("perplexity_search", {"query": "what is asyncio"})
        parsed = json.loads(result)

        assert "answer" in parsed
        assert "asyncio" in parsed["answer"]
        assert "citations" in parsed
        assert len(parsed["citations"]) == 2
        assert "docs.python.org" in parsed["citations"][0]


async def test_search_without_citations():
    registry = ToolRegistry()
    register_perplexity_tool(registry, api_key="pplx-test")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "The answer is 42."}}],
    }

    with patch("buddy_bot.tools.perplexity.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client

        result = await registry.dispatch("perplexity_search", {"query": "meaning of life"})
        parsed = json.loads(result)

        assert parsed["answer"] == "The answer is 42."
        assert "citations" not in parsed


async def test_search_api_error():
    registry = ToolRegistry()
    register_perplexity_tool(registry, api_key="pplx-test")

    with patch("buddy_bot.tools.perplexity.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client

        result = await registry.dispatch("perplexity_search", {"query": "test"})
        parsed = json.loads(result)
        assert "error" in parsed


async def test_correct_api_request_format():
    """Verify the API request uses the correct format."""
    registry = ToolRegistry()
    register_perplexity_tool(registry, api_key="pplx-test-key")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "answer"}}],
    }

    with patch("buddy_bot.tools.perplexity.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client

        await registry.dispatch("perplexity_search", {"query": "test query"})

        # Verify correct URL and headers
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://api.perplexity.ai/chat/completions"
        assert "Bearer pplx-test-key" in call_args.kwargs["headers"]["Authorization"]
        assert call_args.kwargs["json"]["model"] == "sonar"
        assert call_args.kwargs["json"]["messages"][0]["content"] == "test query"
