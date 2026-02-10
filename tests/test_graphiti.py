"""Tests for buddy_bot.graphiti module."""

import json

import httpx
import pytest

from buddy_bot.graphiti import GraphitiClient


def _mcp_response(result):
    return httpx.Response(
        200,
        json={
            "jsonrpc": "2.0",
            "id": "test",
            "result": {"content": [{"type": "text", "text": result}]},
        },
    )


def _transport(handler):
    return httpx.MockTransport(handler)


def _mock_client(handler):
    """Create an AsyncClient with mock transport and base_url."""
    return httpx.AsyncClient(transport=_transport(handler), base_url="http://test:8000")


async def test_health_check_ok():
    def handler(request):
        if request.url.path == "/health":
            return httpx.Response(200)
        return httpx.Response(404)

    client = GraphitiClient("http://test:8000")
    client._client = _mock_client(handler)
    assert await client.health_check() is True
    await client.close()


async def test_health_check_fail():
    def handler(request):
        raise httpx.ConnectError("down")

    client = GraphitiClient("http://test:8000")
    client._client = _mock_client(handler)
    assert await client.health_check() is False
    await client.close()


async def test_get_episodes_sends_correct_payload():
    sent = {}

    def handler(request):
        if request.url.path == "/mcp/":
            sent.update(json.loads(request.content))
            return _mcp_response([{"name": "ep1", "body": "test"}])
        return httpx.Response(404)

    client = GraphitiClient("http://test:8000")
    client._client = _mock_client(handler)
    await client.get_episodes(group_ids=["main"], max_episodes=3)
    assert sent["method"] == "tools/call"
    assert sent["params"]["name"] == "get_episodes"
    assert sent["params"]["arguments"]["max_episodes"] == 3
    await client.close()


async def test_search_facts_sends_correct_payload():
    sent = {}

    def handler(request):
        if request.url.path == "/mcp/":
            sent.update(json.loads(request.content))
            return _mcp_response([{"fact": "test"}])
        return httpx.Response(404)

    client = GraphitiClient("http://test:8000")
    client._client = _mock_client(handler)
    await client.search_facts("pending items", group_ids=["main"])
    assert sent["params"]["name"] == "search_memory_facts"
    assert sent["params"]["arguments"]["query"] == "pending items"
    await client.close()


async def test_search_nodes_sends_correct_payload():
    sent = {}

    def handler(request):
        if request.url.path == "/mcp/":
            sent.update(json.loads(request.content))
            return _mcp_response([{"node": "test"}])
        return httpx.Response(404)

    client = GraphitiClient("http://test:8000")
    client._client = _mock_client(handler)
    await client.search_nodes("project X")
    assert sent["params"]["name"] == "search_nodes"
    assert sent["params"]["arguments"]["query"] == "project X"
    await client.close()


async def test_add_memory_sends_correct_payload():
    sent = {}

    def handler(request):
        if request.url.path == "/mcp/":
            sent.update(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": "test",
                    "result": {"content": [{"type": "text", "text": {"ok": True}}]},
                },
            )
        return httpx.Response(404)

    client = GraphitiClient("http://test:8000")
    client._client = _mock_client(handler)
    await client.add_memory("summary", "User asked about X")
    assert sent["params"]["name"] == "add_memory"
    assert sent["params"]["arguments"]["name"] == "summary"
    assert sent["params"]["arguments"]["episode_body"] == "User asked about X"
    assert sent["params"]["arguments"]["group_id"] == "main"
    await client.close()


async def test_http_error_returns_empty():
    def handler(request):
        return httpx.Response(500)

    client = GraphitiClient("http://test:8000")
    client._client = _mock_client(handler)
    result = await client.get_episodes()
    assert result == []
    await client.close()


async def test_connection_error_returns_empty():
    def handler(request):
        raise httpx.ConnectError("timeout")

    client = GraphitiClient("http://test:8000")
    client._client = _mock_client(handler)
    result = await client.search_facts("test")
    assert result == []
    await client.close()
