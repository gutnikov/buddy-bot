"""Perplexity Sonar search tool — LLM-powered web search with citations."""

import json
import logging

import httpx

from buddy_bot.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

PERPLEXITY_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Search query — works best with natural language questions",
        },
    },
    "required": ["query"],
}


def register_perplexity_tool(registry: ToolRegistry, api_key: str = "") -> None:
    async def handle_perplexity_search(input: dict) -> str:
        if not api_key:
            return json.dumps({"error": "Perplexity search is not configured. Set PERPLEXITY_API_KEY."})

        query = input["query"]
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.perplexity.ai/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "sonar",
                        "messages": [
                            {"role": "user", "content": query},
                        ],
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            # Extract answer and citations
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

    registry.register(
        "perplexity_search",
        "Search the web using Perplexity AI for synthesized answers with citations. Best for questions needing research and analysis.",
        PERPLEXITY_SEARCH_SCHEMA,
        handle_perplexity_search,
    )
