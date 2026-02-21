# Progress Notifications via MCP Tool

## Problem

When a user sends a message, the bot processes it silently for up to 120 seconds.
The only feedback is a "typing..." indicator, which tells the user nothing about
what the bot is actually doing. Users think nothing is happening.

## Solution

Add a `notify_progress` MCP tool that lets Claude send intermediate progress
messages directly to the user's Telegram chat during processing.

Claude decides what to say and when — "On it!", "Searching my memory...",
"Almost done!" — giving natural, contextual feedback.

## Architecture

```
User sends message
    → Bot receives, spawns Claude CLI
        → Claude calls notify_progress("On it!", chat_id)
            → MCP server POSTs to Telegram Bot API
                → User sees "On it!" in chat
        → Claude does work (memory retrieval, etc.)
        → Claude calls notify_progress("Almost done!", chat_id)
            → User sees "Almost done!"
        → Claude produces final response
    → Bot sends final response
```

The MCP server calls the Telegram Bot API directly using `urllib.request`.
No IPC between MCP server and bot process needed.

## Components Changed

### 1. `src/buddy_bot/mcp_server.py`

Add `notify_progress` tool:
- Input: `{ "chat_id": string, "message": string }`
- Reads `TELEGRAM_TOKEN` from environment
- POSTs to `https://api.telegram.org/bot<TOKEN>/sendMessage`
- Uses `urllib.request` (stdlib, zero new dependencies)
- Best-effort: logs errors but doesn't crash on failure

### 2. `src/buddy_bot/prompt.py`

Add instructions for Claude about the tool:
- Use it to acknowledge receipt ("On it!")
- Use it for long operations ("Searching my memory...")
- Don't overuse — 1-2 progress messages per interaction is typical
- The chat_id is provided in the prompt context

### 3. No changes to

- `executor.py` — no IPC, stream parsing unchanged
- `bot.py` — progress messages bypass the bot entirely
- `buffer.py`, `history.py`, `config.py` — untouched

## Design Decisions

- **stdlib only**: `urllib.request` avoids adding dependencies. The MCP server
  runs synchronously anyway (MCP SDK handles async wrapper).
- **Claude controls content**: More natural than mechanical "Searching memory..."
  messages. Claude understands context and can craft appropriate messages.
- **Best-effort delivery**: If Telegram API fails, we log and continue. Progress
  is nice-to-have, not critical path.
- **Messages kept in chat**: Progress messages are not deleted after the final
  response. Keeps implementation simple.
- **Regular messages**: Sent as standalone messages, not replies to the original.

## Definition of Done

- [ ] `notify_progress` tool added to MCP server with Telegram API integration
- [ ] Prompt updated with usage guidelines for the tool
- [ ] Unit tests for the new tool (mocked HTTP calls)
- [ ] Unit tests for prompt changes
- [ ] CI passes (lint + tests)
