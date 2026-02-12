# Claude Code Context — Buddy Bot

## Project Overview

Buddy Bot is a Telegram personal assistant powered by Claude Code CLI (`claude -p`). It uses the Graphiti knowledge graph for long-term memory (via MCP), SQLite for conversation history and todos, and integrates with Google Calendar, Gmail, Tavily, and Perplexity APIs via an MCP tools server.

The bot receives messages via Telegram, batches them with a trailing-edge debounce, builds a prompt, spawns `claude -p` as a subprocess (which handles the entire tool loop via MCP), and sends the response back to Telegram.

## Tech Stack

- **Python 3.12** with async/await throughout
- **Claude Code CLI** (`claude -p`) — LLM backbone, handles tool loop internally
- **MCP** (Model Context Protocol) — tool interface between Claude and bot tools
- **python-telegram-bot** — Telegram integration (polling mode)
- **Graphiti** (zepai/knowledge-graph-mcp) — Long-term memory via MCP (accessed by Claude through mcp-remote)
- **SQLite** — Conversation history, fallback context, todo list, OAuth tokens
- **Yandex SpeechKit** — Voice message transcription (STT)
- **httpx** — Async HTTP client for Tavily, Perplexity, SpeechKit
- **Pydantic** — Settings validation from environment variables
- **Docker Compose** — Deployment (buddy-bot + graphiti-mcp)
- **Node.js** — Required for Claude Code CLI and mcp-remote

## Architecture

```
Telegram message → bot.py → MessageBuffer → main.py processing loop
                                                    ↓
                                            executor.py (ClaudeExecutor)
                                                    ↓
                                        claude -p subprocess
                                        --output-format stream-json --verbose
                                        --mcp-config config/mcp-config.json
                                        --allowedTools mcp__*
                                                    ↓
                                        MCP tools (handled by Claude Code):
                                          - graphiti (via mcp-remote)
                                          - buddy-bot-tools (todo, calendar, email, search, time)
                                                    ↓
                                        JSONL result → parse → send to Telegram
```

Key simplification: No tool_use/tool_result loop in Python. Claude Code handles it all.

## Project Structure

```
src/buddy_bot/
├── main.py              # BuddyBot class — wires components, processing loop
├── config.py            # Pydantic Settings from env vars, cached singleton
├── bot.py               # Telegram handlers, auth, voice transcription, message splitting, 👀 reaction
├── speechkit.py         # Yandex SpeechKit STT client (voice → text)
├── buffer.py            # Trailing-edge debounce (asyncio.Event-based)
├── executor.py          # Spawns `claude -p`, parses JSONL output, session resume
├── prompt.py            # Single prompt builder for `claude -p`
├── progress.py          # Maps tool_use blocks to user-facing progress messages
├── history.py           # SQLite conversation turn store (async via to_thread)
├── todo.py              # SQLite todo/task store
├── typing_indicator.py  # Telegram "typing..." action loop
├── mcp_server.py        # MCP stdio server wrapping all non-Graphiti tools
└── tools/
    └── google_auth.py   # OAuth2 token management with SQLite persistence

config/
├── mcp-config.json      # MCP server configuration for Claude Code CLI
└── graphiti-config.yaml # Graphiti LLM/embedder config
```

## Key Patterns

### Claude Code CLI Executor
`ClaudeExecutor` spawns `claude -p <prompt>` as a subprocess with `--output-format stream-json --verbose --mcp-config <path> --allowedTools mcp__*`. It reads JSONL stdout line-by-line, tracking `system` (session_id), `assistant` (tool_use progress), and `result` (final text) messages. Empty results trigger session resume with `--resume <session_id>`.

### MCP Tools Server
`mcp_server.py` is a stdio MCP server (run as `python -m buddy_bot.mcp_server`) exposing 13 tools: todo (4), calendar (3), email (3), web_search, perplexity_search, get_current_time. Graphiti tools are provided separately via mcp-remote. Config in `config/mcp-config.json`.

### Async everywhere
All I/O is async. SQLite operations use `asyncio.to_thread` to avoid blocking. The Telegram bot and Claude CLI subprocess are all async.

### Per-chat processing loop
`BuddyBot._processing_loop(chat_id)` is the state machine: IDLE → DEBOUNCE → DRAIN → PROCESS → CHECK BUFFER → IDLE. One loop per chat, with `asyncio.Lock` per chat_id for serial execution.

### Message batching
`MessageBuffer` implements trailing-edge debounce. Messages arriving within `DEBOUNCE_DELAY` seconds are batched into a single prompt.

### Prompt structure
Single `build_prompt()` function producing one string for `claude -p`:
1. System context (persona, rules, stdout instructions, datetime)
2. Chat ID for tool context
3. Conversation history (recent turns from SQLite)
4. Retrieval instructions (memory tool use steps)
5. Current messages (JSON array of events)
6. Fallback context (only after a previous failure)

### Error handling
- Claude CLI failure → re-queue messages in buffer, wait 30s
- 3 consecutive failures → drop messages, notify user
- Fallback context: saved on failure, loaded on next attempt, cleared on success
- Timeout: configurable `CLAUDE_TIMEOUT` (default 120s), kills subprocess on expiry

## Build & Test Commands

```bash
# Build Docker image
docker build -t buddy-bot-test .

# Run tests in Docker (standard approach)
docker run --rm -v ./tests:/app/tests buddy-bot-test \
  sh -c "pip install pytest pytest-asyncio && pytest tests/ -v"

# Run specific test file
docker run --rm -v ./tests:/app/tests buddy-bot-test \
  sh -c "pip install pytest pytest-asyncio && pytest tests/test_executor.py -v"

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

## Secrets Management

Secrets are managed centrally via **SOPS + AGE** in the `alex/secrets` Gitea repo (`/home/deploy/work/secrets/secrets/`).

- Encrypted files: `projects/buddy-bot/secrets/{dev,staging,production}.enc.yaml`
- Render `.env` from encrypted store: `make render-env` (or `make render-env ENV=dev`)
- Edit secrets: `cd /home/deploy/work/secrets/secrets && sops projects/buddy-bot/secrets/production.enc.yaml`
- Deploy with fresh secrets: `make deploy` (renders `.env` then runs `docker compose up -d`)
- The `.env` file is gitignored — never commit plaintext secrets
- AGE private key must be at `~/.config/sops/age/keys.txt`
- `ANTHROPIC_API_KEY` is consumed by Claude Code CLI directly from environment

## Important Conventions

- **No Python on host** — Tests always run inside Docker containers. The host has Docker but no Python/pip.
- **Tests mount volume** — Source is baked into the image, but tests are mounted at runtime (`-v ./tests:/app/tests`) for fast iteration without rebuild.
- **Rebuild after source changes** — `docker build -t buddy-bot-test .` is needed when source files change (tests are volume-mounted so test changes don't need a rebuild).
- **All mocks, no real APIs** — Tests never call real external services. Claude CLI, Telegram, Graphiti, Tavily, Perplexity, SpeechKit are all mocked.
- **AsyncMock for async, MagicMock for sync** — Use `MagicMock` for sync response objects, `AsyncMock` for async functions.
- **Settings in tests** — Use the `REQUIRED_SETTINGS` dict pattern with `Settings(**REQUIRED_SETTINGS)`. Override specific fields by spreading: `Settings(**{**REQUIRED_SETTINGS, "field": "value"})`.

## Gotchas

- `history.get_fallback()` is destructive — it deletes the fallback row on read (consume-once semantics).
- `send_response` in `bot.py` splits messages >4096 chars at paragraph boundaries before sending.
- Voice support is opt-in — when `SPEECHKIT_API_KEY` is empty, the `filters.VOICE` handler is not registered and voice messages are silently ignored.
- `speechkit.recognize()` returns `str | None`: non-empty string = success, empty string = silence/noise, `None` = error.
- Telegram voice messages are OGG/Opus — sent directly to SpeechKit with no format conversion needed.
- MCP tool names are prefixed by Claude Code (e.g., `mcp__buddy-bot-tools__todo_add`). The `progress.py` module strips this prefix when looking up progress messages.
- Todo tools take `chat_id` as a parameter (passed by Claude, instructed via prompt) for per-chat isolation.
- Google Calendar/Gmail operations in the MCP server use `asyncio.to_thread` since the Google API client is synchronous.
