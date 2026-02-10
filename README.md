# Buddy Bot

A persistent Telegram personal assistant powered by Claude, with long-term memory via the Graphiti knowledge graph.

Buddy Bot remembers past conversations, manages your calendar and email, keeps a todo list, and searches the web — all through natural Telegram chat.

## Features

- **Long-term memory** — Stores and retrieves conversation context using [Graphiti](https://github.com/getzep/graphiti) knowledge graph (episodes, facts, entities)
- **Conversation continuity** — SQLite-backed history with fallback context recovery on failures
- **Todo list** — Built-in task management with priorities, due dates, and per-chat isolation
- **Google Calendar** — List, create, and delete events via Google Calendar API
- **Gmail** — List, read, and send emails with reply threading support
- **Web search** — Tavily for link discovery, Perplexity Sonar for synthesized research answers
- **Message batching** — Trailing-edge debounce groups rapid messages into a single prompt
- **Tool use loop** — Claude autonomously calls tools (memory retrieval, search, calendar, etc.) and iterates up to 20 rounds
- **Graceful error handling** — Retry with exponential backoff for API errors, fallback context on failures, 3-strike message drop with user notification

## Architecture

```
Telegram ──► bot.py (auth, extract, react 👀)
                │
                ▼
           buffer.py (trailing-edge debounce)
                │
                ▼
           main.py (per-chat processing loop)
                │
                ▼
           processor.py (prompt → Claude API → tool loop → response)
                │
          ┌─────┼──────────┬──────────┐
          ▼     ▼          ▼          ▼
       memory  todo    calendar    search
      (Graphiti) (SQLite) (Google) (Tavily/Perplexity)
```

**Key components:**

| Module | Purpose |
|--------|---------|
| `config.py` | Pydantic settings from environment variables |
| `bot.py` | Telegram handlers, authorization, message splitting |
| `buffer.py` | Async trailing-edge debounce for message batching |
| `history.py` | SQLite conversation turn storage with per-turn truncation |
| `todo.py` | SQLite todo/task store with CRUD operations |
| `graphiti.py` | MCP JSON-RPC client for Graphiti knowledge graph |
| `prompt.py` | 5-section prompt builder (system, history, retrieval, messages, fallback) |
| `processor.py` | Claude API client with tool_use loop and retry logic |
| `retry.py` | Generic async retry utility with exponential backoff |
| `typing_indicator.py` | Async Telegram "typing..." action loop |
| `tools/` | Tool registry + handlers (memory, todo, calendar, email, search, time) |

## Prerequisites

- Docker and Docker Compose
- API keys: Anthropic, OpenAI, Voyage AI
- Telegram bot token (via [@BotFather](https://t.me/BotFather))
- Optional: Tavily API key, Perplexity API key, Google OAuth credentials

## Quick Start

1. **Clone and configure:**
   ```bash
   git clone https://github.com/gutnikov/buddy-bot.git
   cd buddy-bot
   cp .env.example .env
   # Edit .env with your API keys
   ```

2. **Start services:**
   ```bash
   docker compose up -d
   ```
   This starts both `buddy-bot` and `graphiti-mcp`. The bot waits for Graphiti's health check before starting.

3. **Talk to your bot** on Telegram. It will react with 👀 on receipt and respond after processing.

## Configuration

All configuration is via environment variables. See `.env.example` for the full list.

**Required:**

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Claude API key |
| `TELEGRAM_TOKEN` | Telegram bot token |
| `TELEGRAM_ALLOWED_CHAT_IDS` | Comma-separated chat IDs allowed to use the bot |
| `OPENAI_API_KEY` | For Graphiti's LLM (gpt-4.1-mini) |
| `VOYAGE_API_KEY` | For Graphiti's embeddings (voyage-4) |

**Optional:**

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL` | `claude-sonnet-4-5-20250929` | Claude model to use |
| `MAX_TOKENS` | `4096` | Max response tokens |
| `TEMPERATURE` | `0.7` | Sampling temperature |
| `HISTORY_TURNS` | `20` | Conversation turns to include in prompt |
| `DEBOUNCE_DELAY` | `5` | Seconds to wait for message batching |
| `USER_TIMEZONE` | `UTC` | Timezone for `get_current_time` tool |
| `TAVILY_API_KEY` | _(empty)_ | Enables web search |
| `PERPLEXITY_API_KEY` | _(empty)_ | Enables Perplexity search |
| `LOG_LEVEL` | `INFO` | Logging level |

## Google OAuth Setup (Calendar & Gmail)

1. Create a Google Cloud project and enable Calendar and Gmail APIs
2. Download OAuth client credentials as `credentials/client_secret.json`
3. On first use, the bot will open a browser for OAuth consent (one-time setup)
4. Tokens are stored in SQLite and auto-refreshed thereafter

For Docker: mount pre-obtained credentials at `/app/credentials/client_secret.json` (read-only).

## Development

**Run tests in Docker:**
```bash
docker build -t buddy-bot-test .
docker run --rm -v ./tests:/app/tests buddy-bot-test \
  sh -c "pip install pytest pytest-asyncio && pytest tests/ -v"
```

**Run tests locally (Python 3.12+):**
```bash
pip install -e ".[dev]"
pytest tests/ -v
```

**Makefile targets:**
```bash
make test    # Run tests (Docker with fallback to local)
make build   # Build Docker image
make up      # docker compose up -d
make down    # docker compose down
```

## Tools

The bot exposes these tools to Claude:

| Tool | Description |
|------|-------------|
| `get_episodes` | Retrieve recent conversation episodes from Graphiti |
| `search_memory_facts` | Search long-term memory for facts and relationships |
| `search_nodes` | Search for entities in the knowledge graph |
| `add_memory` | Save a conversation summary to long-term memory |
| `todo_add` | Add a task with optional due date and priority |
| `todo_list` | List tasks, filter by status or due date |
| `todo_complete` | Mark a task as done |
| `todo_delete` | Delete a task |
| `calendar_list_events` | List upcoming Google Calendar events |
| `calendar_create_event` | Create a calendar event |
| `calendar_delete_event` | Delete a calendar event |
| `email_list_messages` | List Gmail messages |
| `email_read_message` | Read a full email |
| `email_send_message` | Send an email (with reply threading) |
| `web_search` | Search the web via Tavily |
| `perplexity_search` | LLM-powered search via Perplexity Sonar |
| `get_current_time` | Get current date/time in configured timezone |

## License

MIT
