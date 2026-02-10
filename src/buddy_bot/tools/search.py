"""Web search tool handler."""

import json
import logging

import httpx

from buddy_bot.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

WEB_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Search query"},
    },
    "required": ["query"],
}


def register_search_tool(registry: ToolRegistry, api_key: str = "") -> None:
    async def handle_web_search(input: dict) -> str:
        if not api_key:
            return json.dumps({"error": "Web search is not configured. Set TAVILY_API_KEY."})

        query = input["query"]
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json={"api_key": api_key, "query": query, "max_results": 5},
                )
                resp.raise_for_status()
                data = resp.json()

            results = []
            for item in data.get("results", []):
                results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "snippet": item.get("content", "")[:300],
                    }
                )
            return json.dumps(results)
        except Exception as e:
            logger.warning("Web search failed: %s", e)
            return json.dumps({"error": f"Web search failed: {e}"})

    registry.register(
        "web_search",
        "Search the web for current information.",
        WEB_SEARCH_SCHEMA,
        handle_web_search,
    )
