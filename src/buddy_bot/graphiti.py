"""Graphiti HTTP client for MCP JSON-RPC calls."""

import logging
import uuid

import httpx

logger = logging.getLogger(__name__)


class GraphitiClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0),
        )

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get("/health")
            return resp.status_code == 200
        except Exception:
            logger.warning("Graphiti health check failed")
            return False

    async def _mcp_call(self, tool_name: str, arguments: dict) -> list | dict:
        """Send an MCP JSON-RPC tools/call request."""
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        try:
            resp = await self._client.post("/mcp/", json=payload)
            resp.raise_for_status()
            data = resp.json()
            result = data.get("result", {})
            # MCP tool results have content array
            if isinstance(result, dict) and "content" in result:
                content = result["content"]
                if isinstance(content, list) and content:
                    return content[0].get("text", content)
            return result
        except Exception:
            logger.warning("Graphiti MCP call %s failed", tool_name, exc_info=True)
            return []

    async def get_episodes(
        self, group_ids: list[str] | None = None, max_episodes: int = 5
    ) -> list:
        if group_ids is None:
            group_ids = ["main"]
        result = await self._mcp_call(
            "get_episodes",
            {"group_ids": group_ids, "max_episodes": max_episodes},
        )
        return result if isinstance(result, list) else []

    async def search_facts(
        self, query: str, group_ids: list[str] | None = None
    ) -> list:
        if group_ids is None:
            group_ids = ["main"]
        result = await self._mcp_call(
            "search_memory_facts",
            {"query": query, "group_ids": group_ids},
        )
        return result if isinstance(result, list) else []

    async def search_nodes(
        self, query: str, group_ids: list[str] | None = None
    ) -> list:
        if group_ids is None:
            group_ids = ["main"]
        result = await self._mcp_call(
            "search_nodes",
            {"query": query, "group_ids": group_ids},
        )
        return result if isinstance(result, list) else []

    async def add_memory(
        self,
        name: str,
        episode_body: str,
        group_id: str = "main",
        source: str = "text",
    ) -> dict:
        result = await self._mcp_call(
            "add_memory",
            {
                "name": name,
                "episode_body": episode_body,
                "group_id": group_id,
                "source": source,
            },
        )
        return result if isinstance(result, dict) else {}

    async def close(self) -> None:
        await self._client.aclose()
