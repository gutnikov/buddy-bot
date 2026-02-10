# Claude Code Context — Buddy Bot

## Project Overview

Buddy Bot is a Telegram personal assistant powered by Claude (Anthropic). It uses the Graphiti knowledge graph for long-term memory, SQLite for conversation history and todos, and integrates with Google Calendar, Gmail, Tavily, and Perplexity APIs.

The bot receives messages via Telegram, batches them with a trailing-edge debounce, builds a multi-section prompt, calls the Claude Messages API with tool use, and sends the response back to Telegram.

## Tech Stack

- **Python 3.12** with async/await throughout
- **Claude Messages API** (anthropic SDK) — LLM backbone with tool_use loop
- **python-telegram-bot** — Telegram integration (polling mode)
- **Graphiti** (zepai/knowledge-graph-mcp) — Long-term memory via MCP JSON-RPC over HTTP
- **SQLite** — Conversation history, fallback context, todo list, OAuth tokens
- **Yandex SpeechKit** — Voice message transcription (STT)
- **httpx** — Async HTTP client for Graphiti, Tavily, Perplexity, SpeechKit
- **Pydantic** — Settings validation from environment variables
- **Docker Compose** — Deployment (buddy-bot + graphiti-mcp)

## Project Structure

```
src/buddy_bot/
├── main.py              # BuddyBot class — wires components, processing loop
├── config.py            # Pydantic Settings from env vars, cached singleton
├── bot.py               # Telegram handlers, auth, voice transcription, message splitting, 👀 reaction
├── speechkit.py         # Yandex SpeechKit STT client (voice → text)
├── buffer.py            # Trailing-edge debounce (asyncio.Event-based)
├── processor.py         # Prompt → Claude API → tool loop → response pipeline
├── prompt.py            # 5-section prompt builder
├── history.py           # SQLite conversation turn store (async via to_thread)
├── todo.py              # SQLite todo/task store
├── graphiti.py          # MCP JSON-RPC client for Graphiti
├── retry.py             # Generic async retry_with_backoff utility
├── typing_indicator.py  # Telegram "typing..." action loop
└── tools/
    ├── registry.py      # Tool definition + dispatch registry
    ├── memory.py        # 4 Graphiti tools (get_episodes, search_facts, etc.)
    ├── todo.py          # 4 todo tools (add, list, complete, delete)
    ├── calendar.py      # 3 Google Calendar tools
    ├── email.py         # 3 Gmail tools
    ├── search.py        # Tavily web search
    ├── perplexity.py    # Perplexity Sonar search
    ├── time.py          # get_current_time
    └── google_auth.py   # OAuth2 token management with SQLite persistence
```

## Key Patterns

### Async everywhere
All I/O is async. SQLite operations use `asyncio.to_thread` to avoid blocking. The Graphiti client, Telegram bot, and Claude API are all async.

### Tool registry pattern
Tools are registered via `ToolRegistry.register(name, description, input_schema, handler)`. The registry produces Claude Messages API tool definitions and dispatches tool calls by name. Each tool module has a `register_*_tools()` function called from `main.py`.

### Per-chat processing loop
`BuddyBot._processing_loop(chat_id)` is the state machine: IDLE → DEBOUNCE → DRAIN → PROCESS → CHECK BUFFER → IDLE. One loop per chat, with `asyncio.Lock` per chat_id for serial execution.

### Message batching
`MessageBuffer` implements trailing-edge debounce. Messages arriving within `DEBOUNCE_DELAY` seconds are batched into a single prompt.

### 5-section prompt
1. System prompt (persona, rules, datetime)
2. Conversation history (recent turns from SQLite)
3. Retrieval instructions (tool use steps for memory)
4. Current messages (JSON array of events)
5. Fallback context (only after a previous failure)

### Error handling
- `retry_with_backoff()` — generic retry with exponential backoff and error classification
- Claude API: 429 → retry with backoff, 5xx → retry once, 529 → 30s backoff
- Processing failure → re-queue messages in buffer, wait 30s
- 3 consecutive failures → drop messages, notify user
- Fallback context: saved on failure, loaded on next attempt, cleared on success

### Chat ID context for tools
Todo tools need to know which chat they serve. A `chat_id_ref` dict is set before each processing cycle and read by tool handlers via closure.

## Build & Test Commands

```bash
# Build Docker image
docker build -t buddy-bot-test .

# Run tests in Docker (standard approach)
docker run --rm -v ./tests:/app/tests buddy-bot-test \
  sh -c "pip install pytest pytest-asyncio && pytest tests/ -v"

# Run specific test file
docker run --rm -v ./tests:/app/tests buddy-bot-test \
  sh -c "pip install pytest pytest-asyncio && pytest tests/test_processor.py -v"

# Run locally (Python 3.12+ required)
pip install -e ".[dev]"
pytest tests/ -v

# Makefile shortcuts
make test    # Docker with local fallback
make build   # docker build
make up      # docker compose up -d
make down    # docker compose down
```

Test configuration: `asyncio_mode = "auto"` in pyproject.toml — all async test functions run automatically without `@pytest.mark.asyncio`.

Docker tests (`test_docker.py`) auto-skip when Docker CLI is unavailable (inside container).

## Important Conventions

- **No Python on host** — Tests always run inside Docker containers. The host has Docker but no Python/pip.
- **Tests mount volume** — Source is baked into the image, but tests are mounted at runtime (`-v ./tests:/app/tests`) for fast iteration without rebuild.
- **Rebuild after source changes** — `docker build -t buddy-bot-test .` is needed when source files change (tests are volume-mounted so test changes don't need a rebuild).
- **All mocks, no real APIs** — Tests never call real external services. Anthropic, Telegram, Graphiti, Tavily, Perplexity, SpeechKit are all mocked.
- **AsyncMock for async, MagicMock for sync** — Use `MagicMock` for sync response objects (e.g., httpx.Response.json() is sync), `AsyncMock` for async functions.
- **Settings in tests** — Use the `REQUIRED_SETTINGS` dict pattern with `Settings(**REQUIRED_SETTINGS)`. Override specific fields by spreading: `Settings(**{**REQUIRED_SETTINGS, "field": "value"})`.

## Gotchas

- `graphiti.py` returns empty lists/dicts on errors (never throws) — memory tools degrade gracefully.
- `history.get_fallback()` is destructive — it deletes the fallback row on read (consume-once semantics).
- The `_api_call` method in `processor.py` uses `retry_with_backoff` which raises `MaxRetriesExceeded` (wrapping the original error) when all retries are exhausted.
- `send_response` in `bot.py` splits messages >4096 chars at paragraph boundaries before sending.
- Tool handlers return JSON strings, never dicts. The registry's `dispatch` method handles JSON serialization for non-string returns.
- Google Calendar/Gmail tools take a `get_credentials` async callable (not credentials directly) — credentials are fetched fresh on each tool invocation.
- Voice support is opt-in — when `SPEECHKIT_API_KEY` is empty, the `filters.VOICE` handler is not registered and voice messages are silently ignored.
- `speechkit.recognize()` returns `str | None`: non-empty string = success, empty string = silence/noise, `None` = error. The caller in `bot.py` maps each case to the appropriate user reply.
- Telegram voice messages are OGG/Opus — sent directly to SpeechKit with no format conversion needed.
