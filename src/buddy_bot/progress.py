"""Map tool_use blocks to user-facing progress messages."""

# Tool name → progress message shown during processing
TOOL_PROGRESS: dict[str, str] = {
    # Memory tools (via Graphiti MCP)
    "get_episodes": "Recalling recent conversations...",
    "search_memory_facts": "Searching memory...",
    "search_nodes": "Looking up entities...",
    "add_memory": "Saving to memory...",
    # Time
    "get_current_time": "Checking the time...",
    # Progress
    "notify_progress": "Sending progress update...",
}


def format_tool_progress(tool_name: str) -> str | None:
    """Return a user-facing progress message for the given tool name.

    MCP tool names may be prefixed (e.g. mcp__buddy-bot-tools__todo_add).
    We strip the prefix and look up the base name.
    """
    # Strip MCP server prefix: mcp__<server>__<tool> → <tool>
    base_name = tool_name
    if base_name.startswith("mcp__"):
        parts = base_name.split("__", 2)
        if len(parts) == 3:
            base_name = parts[2]

    return TOOL_PROGRESS.get(base_name)
