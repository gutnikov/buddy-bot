"""Graphiti memory tool handlers."""

import json
import logging

from buddy_bot.graphiti import GraphitiClient
from buddy_bot.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

GET_EPISODES_SCHEMA = {
    "type": "object",
    "properties": {
        "group_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Memory group IDs to search",
            "default": ["main"],
        },
        "max_episodes": {
            "type": "integer",
            "description": "Maximum number of episodes to retrieve",
            "default": 5,
        },
    },
    "required": [],
}

SEARCH_MEMORY_FACTS_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Natural language search query",
        },
        "group_ids": {
            "type": "array",
            "items": {"type": "string"},
            "default": ["main"],
        },
    },
    "required": ["query"],
}

SEARCH_NODES_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Entity or topic to search for",
        },
        "group_ids": {
            "type": "array",
            "items": {"type": "string"},
            "default": ["main"],
        },
    },
    "required": ["query"],
}

ADD_MEMORY_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Short descriptive name for this memory episode",
        },
        "episode_body": {
            "type": "string",
            "description": "Free-form text summary of the interaction",
        },
        "group_id": {"type": "string", "default": "main"},
        "source": {"type": "string", "default": "text"},
    },
    "required": ["name", "episode_body"],
}


def register_memory_tools(registry: ToolRegistry, graphiti_client: GraphitiClient) -> None:
    """Register all 4 Graphiti memory tools with the registry."""

    async def handle_get_episodes(input: dict) -> str:
        group_ids = input.get("group_ids", ["main"])
        max_episodes = input.get("max_episodes", 5)
        result = await graphiti_client.get_episodes(group_ids, max_episodes)
        return json.dumps(result) if not isinstance(result, str) else result

    async def handle_search_memory_facts(input: dict) -> str:
        query = input["query"]
        group_ids = input.get("group_ids", ["main"])
        result = await graphiti_client.search_facts(query, group_ids)
        return json.dumps(result) if not isinstance(result, str) else result

    async def handle_search_nodes(input: dict) -> str:
        query = input["query"]
        group_ids = input.get("group_ids", ["main"])
        result = await graphiti_client.search_nodes(query, group_ids)
        return json.dumps(result) if not isinstance(result, str) else result

    async def handle_add_memory(input: dict) -> str:
        name = input["name"]
        episode_body = input["episode_body"]
        group_id = input.get("group_id", "main")
        source = input.get("source", "text")
        result = await graphiti_client.add_memory(name, episode_body, group_id, source)
        return json.dumps(result) if not isinstance(result, str) else result

    registry.register(
        "get_episodes",
        "Retrieve the most recent conversation episodes from long-term memory. Use this at the start of every interaction to get recent context.",
        GET_EPISODES_SCHEMA,
        handle_get_episodes,
    )
    registry.register(
        "search_memory_facts",
        "Search long-term memory for facts and relationships. Use for finding pending tasks, user preferences, past decisions, or any specific topic.",
        SEARCH_MEMORY_FACTS_SCHEMA,
        handle_search_memory_facts,
    )
    registry.register(
        "search_nodes",
        "Search for entities (people, projects, topics) in long-term memory. Use when you need to know about a specific entity or topic.",
        SEARCH_NODES_SCHEMA,
        handle_search_nodes,
    )
    registry.register(
        "add_memory",
        "Save a conversation summary to long-term memory. Call this after every interaction with a summary of: what the user said, what you responded, actions taken, and pending items.",
        ADD_MEMORY_SCHEMA,
        handle_add_memory,
    )
