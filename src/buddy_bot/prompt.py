"""Prompt assembly — builds a single prompt string for `claude -p`."""

import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from buddy_bot.history import Turn

SYSTEM_CONTEXT = """You are a persistent personal assistant communicating with your user via Telegram.
You maintain conversation continuity using the Graphiti knowledge graph (via MCP tools).

At the start of each interaction, retrieve recent episodes and relevant facts.
After responding, save an episode summarizing this interaction.
If no episodes or facts are found, this is your first conversation — introduce
yourself naturally and learn about your user.

RESPONSE RULES:
- Your stdout is sent directly as a Telegram message.
- Output ONLY the message text. No internal reasoning or meta-commentary.
- Keep responses concise and conversational.
- Use Telegram-compatible formatting (bold, italic, code) sparingly.
- You MUST produce a text response for every interaction.
- Do NOT use any file, bash, or code-editing tools. Only use MCP tools."""

RETRIEVAL_INSTRUCTIONS = """Before responding, follow these steps IN ORDER:

Step 1 — Retrieve context:
1. Call get_episodes(group_ids=["main"], max_episodes=5) for recent conversation context
2. Call search_memory_facts(query="pending items, open tasks", group_ids=["main"])
3. You may call search_memory_facts or search_nodes with other queries based on the message

Step 2 — Respond to the user's message using the retrieved context

Step 3 — Save memory:
Call add_memory with a free-form text summary of: what the user said, what you
responded, what actions you took, and any pending items.
Use group_id="main", source="text", and a descriptive name."""


def build_prompt(
    chat_id: str,
    history_turns: list[Turn],
    events: list[dict],
    fallback_text: str | None = None,
    timezone: str = "UTC",
) -> str:
    """Build a single prompt string for `claude -p`.

    Combines system context, conversation history, retrieval instructions,
    current messages, and optional fallback context.
    """
    sections: list[str] = []

    # Section 1: System context with current datetime
    now_str = _get_current_datetime(timezone)
    sections.append(SYSTEM_CONTEXT)
    sections.append(f"The current date and time is: {now_str}")
    sections.append(f"The user's chat_id is: {chat_id}")

    # Section 2: Conversation history
    if history_turns:
        lines = ["Recent conversation:"]
        for turn in history_turns:
            lines.append(f"User: {turn.user_text}")
            lines.append(f"Assistant: {turn.bot_response}")
        sections.append("\n".join(lines))

    # Section 3: Retrieval instructions
    sections.append(RETRIEVAL_INSTRUCTIONS)

    # Section 4: Current messages
    event_items = [
        {"text": e.get("text", ""), "from": e.get("from", ""), "timestamp": e.get("timestamp", "")}
        for e in events
    ]
    sections.append(f"New message(s) from the user:\n{json.dumps(event_items, indent=2)}")

    # Section 5: Fallback context (only after failed previous run)
    if fallback_text:
        sections.append(
            f"Previous interaction context (retry after failure):\n{fallback_text}"
        )

    return "\n\n".join(sections)


def _get_current_datetime(tz_name: str) -> str:
    """Get current datetime string in the given timezone."""
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, KeyError):
        tz = ZoneInfo("UTC")
    return datetime.now(tz).isoformat()
