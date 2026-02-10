"""Prompt assembly — 5-section prompt builder."""

import json

from buddy_bot.history import Turn

SYSTEM_TEMPLATE = """You are a persistent personal assistant communicating with your user via Telegram.
You maintain conversation continuity using the Graphiti knowledge graph.

At the start of each interaction, retrieve recent episodes and relevant facts.
After responding, save an episode summarizing this interaction.
If no episodes or facts are found, this is your first conversation — introduce
yourself naturally and learn about your user.

RESPONSE RULES:
- Your response is sent directly as a Telegram message.
- Output ONLY the message text. No internal reasoning or meta-commentary.
- Keep responses concise and conversational.
- Use Telegram-compatible formatting (bold, italic, code) sparingly.
- You MUST produce a text response for every interaction.

The current date and time is: {current_datetime}"""

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


def build_system_prompt(current_datetime: str) -> str:
    """Build Section 1: System Context."""
    return SYSTEM_TEMPLATE.format(current_datetime=current_datetime)


def build_user_prompt(
    history_turns: list[Turn],
    events: list[dict],
    fallback_text: str | None = None,
) -> str:
    """Build Sections 2-5 as the user message content."""
    sections: list[str] = []

    # Section 2: Conversation History
    if history_turns:
        lines = ["Recent conversation:"]
        for turn in history_turns:
            lines.append(f"User: {turn.user_text}")
            lines.append(f"Assistant: {turn.bot_response}")
        sections.append("\n".join(lines))

    # Section 3: Retrieval Instructions (always present)
    sections.append(RETRIEVAL_INSTRUCTIONS)

    # Section 4: Current Messages (always present)
    event_items = [
        {"text": e.get("text", ""), "from": e.get("from", ""), "timestamp": e.get("timestamp", "")}
        for e in events
    ]
    sections.append(f"New message(s) from the user:\n{json.dumps(event_items, indent=2)}")

    # Section 5: Fallback Context (only after failed previous run)
    if fallback_text:
        sections.append(
            f"Previous interaction context (retry after failure):\n{fallback_text}"
        )

    return "\n\n".join(sections)
