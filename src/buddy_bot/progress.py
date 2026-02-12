"""Map tool_use blocks to user-facing progress messages."""

# Tool name → progress message shown during processing
TOOL_PROGRESS: dict[str, str] = {
    # Memory tools (via Graphiti MCP)
    "get_episodes": "Recalling recent conversations...",
    "search_memory_facts": "Searching memory...",
    "search_nodes": "Looking up entities...",
    "add_memory": "Saving to memory...",
    # Todo tools
    "todo_add": "Adding task...",
    "todo_list": "Checking tasks...",
    "todo_complete": "Completing task...",
    "todo_delete": "Removing task...",
    # Calendar tools
    "calendar_list_events": "Checking calendar...",
    "calendar_create_event": "Creating event...",
    "calendar_delete_event": "Removing event...",
    # Email tools
    "email_list_messages": "Checking email...",
    "email_read_message": "Reading email...",
    "email_send_message": "Sending email...",
    # Search tools
    "web_search": "Searching the web...",
    "perplexity_search": "Researching...",
    # Time
    "get_current_time": "Checking the time...",
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
