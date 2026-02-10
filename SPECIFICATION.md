# Buddy Bot — Telegram Personal Assistant Specification

## 1. Project Overview

### What It Does

Buddy Bot is a personal assistant that lives in Telegram direct messages. It communicates naturally in 1-on-1 conversations, remembers everything across sessions using a temporal knowledge graph, and has access to tools like calendar and email. It feels like texting a knowledgeable friend who never forgets.

### Who It's For

A single user (the bot owner) who wants a persistent AI assistant accessible from Telegram on any device. The bot is private — only the authorized user can interact with it.

### Design Philosophy

The reference implementation ([gutnikov/orca](https://github.com/gutnikov/orca), now "Code✻Hub") uses a complex multi-service architecture: n8n for webhook routing, a session monitor, a sidecar, and the `claude -p` CLI as a subprocess. This is over-engineered for a simple 1-on-1 Telegram bot.

Buddy Bot takes only what's relevant from orca:
- **Keep**: Graphiti temporal memory, conversation history in SQLite, debounce batching, typing indicators, prompt structure with system context + history + retrieval instructions + events
- **Drop**: n8n (handle webhooks directly), session monitor + sidecar (not needed), `claude -p` CLI (use Anthropic API directly), MCP protocol (use Claude's native tool_use)

The result is a **single Python service** in a **single Docker container** with a Graphiti sidecar.

---

## 2. Functional Requirements

### 2.1 Natural Conversational Behavior

The bot must behave like a natural conversational partner in Telegram DMs:

- Respond to messages with concise, conversational text
- Support multi-message sequences (user sends several messages before bot responds)
- Show "typing..." indicator while processing
- React with 👀 emoji on received messages to acknowledge receipt before processing
- Handle text messages, photos with captions, voice messages (transcribed), and documents
- Gracefully handle messages that arrive while a response is being generated (queue them)
- Never greet the user with "Hello, how can I help you?" on every message — maintain conversational continuity

### 2.2 Conversation History

**Adapted from orca's `src/executor/history.py` and `src/executor/prompt.py`**

The bot maintains a local SQLite database of raw conversation turns, providing exact wording for recent exchanges.

| Parameter | Value | Configurable Via |
|-----------|-------|-----------------|
| History depth | 20 messages (10 user + 10 assistant turns) | `HISTORY_TURNS=20` |
| Per-message truncation | 500 characters | `HISTORY_MAX_CHARS=500` |
| Storage | SQLite file | `HISTORY_DB=/data/history.db` |
| Scope | Per chat_id | Automatic |

**How it works:**
1. After each successful response, save the user message(s) and bot response as a turn
2. Before each API call, retrieve the last N turns for the chat_id
3. Format as alternating `User:` / `Assistant:` blocks in the prompt
4. Truncate individual messages to prevent context bloat

**Schema** (adapted from orca's `HistoryStore`):

```sql
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT NOT NULL,
    user_text TEXT NOT NULL,
    bot_response TEXT NOT NULL,
    duration_ms INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_turns_chat_id ON turns(chat_id);
```

**Why both history and Graphiti memory**: Graphiti stores semantic summaries — great for "what tasks are pending?" but lossy on exact wording. Conversation history stores raw text — essential for "no, I meant the other thing" where exact context matters. Both are included in every prompt (same approach as orca).

### 2.3 Zep/Graphiti Temporal Memory

**Adapted from orca's `specs/graphiti-memory-continuity.md` and `how-memory-works.md`**

The bot uses [Graphiti](https://github.com/getzep/graphiti) (Zep's temporal knowledge graph) for persistent long-term memory across all conversations.

#### Two-Layer Memory Model

**Layer 1: Episodes (immediate context)**
- Raw conversation summaries stored chronologically
- `get_episodes(last_n=5)` retrieves the most recent summaries
- Purpose: maintain the immediate conversational thread

**Layer 2: Knowledge Graph (long-term memory)**
- Entities, facts, and relationships extracted automatically by Graphiti's LLM
- Facts have `valid_at`/`invalid_at` timestamps (bi-temporal model)
- Entity summaries evolve as new episodes reference them
- `search_memory_facts` and `search_nodes` retrieve from the entire history
- Purpose: remember everything ever discussed

#### Memory Flow Per Message

```
1. USER SENDS MESSAGE
        │
        ▼
2. RETRIEVE CONTEXT
   ├── get_episodes(group_ids=["main"], max_episodes=5)      ← recent conversation
   ├── search_memory_facts("pending items, open tasks")       ← active commitments
   └── (optional) search_memory_facts("<dynamic query>")      ← based on message content
        │
        ▼
3. GENERATE RESPONSE (Claude API with full context)
        │
        ▼
4. SAVE EPISODE
   └── add_memory(name="<summary>", episode_body="<detail>", group_id="main")
        │
        ▼
5. DELIVER RESPONSE TO TELEGRAM
```

#### Episode Content

Each saved episode is a free-form text summary containing:
- What the user said
- What the bot responded
- Actions taken (tool calls, lookups)
- Pending items (promises, open tasks, reminders)
- Decisions made (user preferences, confirmed choices)

Graphiti's LLM automatically extracts entities and relationships from episode text, building the knowledge graph incrementally.

#### Fact Supersession

When the user changes a preference (e.g., "I prefer TypeScript" → later "I switched to Python"), Graphiti automatically invalidates the old fact and creates a new one. The bot does not need to manage fact lifecycle.

#### Retrieval Strategy

| Need | Method | Rationale |
|------|--------|-----------|
| Last few exchanges | `get_episodes(last_n=5)` | Chronological, always latest |
| Open commitments | `search_memory_facts("pending items")` | Active relationship edges |
| User profile / preferences | `search_nodes` | Entity summaries evolve over time |
| Specific past topic | `search_memory_facts("<query>")` | Semantic + temporal search |

### 2.4 Claude as the LLM Backend

The bot uses the Anthropic Messages API directly (not the `claude -p` CLI).

**Why not `claude -p`?**
- Orca uses `claude -p` because it needs Claude Code's built-in tools (Read, Write, Edit, Bash, etc.) for software development tasks
- Buddy Bot doesn't need code editing tools — it needs calendar, email, and knowledge retrieval
- Direct API gives us: streaming support, precise token control, native tool_use, no Node.js/CLI dependency, lower overhead

**API Configuration:**

| Parameter | Value |
|-----------|-------|
| Model | `claude-sonnet-4-5-20250929` (default, configurable) |
| Max tokens | 4096 |
| Temperature | 0.7 |
| System prompt | See Section 2.5 |
| Tools | See Section 4 |
| Streaming | Yes (for typing indicator timing) |

### 2.5 Prompt Structure

**Adapted from orca's `src/executor/prompt.py` `build_prompt()` function**

The prompt is assembled from up to 5 sections, joined by double newlines:

```
┌─────────────────────────────────────┐
│ Section 1: System Context           │  ← Always present
├─────────────────────────────────────┤
│ Section 2: Conversation History     │  ← Present after first exchange
├─────────────────────────────────────┤
│ Section 3: Retrieval Instructions   │  ← Always present
├─────────────────────────────────────┤
│ Section 4: Current Message(s)       │  ← Always present
├─────────────────────────────────────┤
│ Section 5: Fallback Context         │  ← Only after failed previous run
└─────────────────────────────────────┘
```

**Section 1 — System Context:**

```
You are a persistent personal assistant communicating with your user via Telegram.
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

The current date and time is: {current_datetime}
```

**Section 2 — Conversation History:**

```
Recent conversation:
User: what's the status on the deployment?
Assistant: Staging deploy succeeded about an hour ago. Want me to kick off production?
User: remind me to review the PR tomorrow
Assistant: Got it! I'll remind you to review the PR tomorrow.
```

**Section 3 — Retrieval Instructions:**

```
Before responding, follow these steps IN ORDER:

Step 1 — Retrieve context:
1. Call get_episodes(group_ids=["main"], max_episodes=5) for recent conversation context
2. Call search_memory_facts(query="pending items, open tasks", group_ids=["main"])
3. You may call search_memory_facts or search_nodes with other queries based on the message

Step 2 — Respond to the user's message using the retrieved context

Step 3 — Save memory:
Call add_memory with a free-form text summary of: what the user said, what you
responded, what actions you took, and any pending items.
Use group_id="main", source="text", and a descriptive name.
```

**Section 4 — Current Message(s):**

```
New message(s) from the user:
[
  {
    "text": "remind me to review the PR tomorrow",
    "from": "alex",
    "timestamp": "2026-02-10T14:30:00Z"
  }
]
```

**Section 5 — Fallback (only after previous failure):**

```
Previous interaction context (retry after failure):
Got it, I'll remind you about the PR review...
```

### 2.6 Message Debouncing

**Adapted from orca's `src/executor/buffer.py` and n8n Wait node**

When users send multiple messages quickly (e.g., typing a thought across 3 messages), the bot should batch them into a single processing run rather than responding to each individually.

| Parameter | Value | Configurable Via |
|-----------|-------|-----------------|
| Debounce delay | 5 seconds | `DEBOUNCE_DELAY=5` |
| Behavior | Trailing edge (wait for silence) | — |

**Algorithm:**
1. Message arrives → add to buffer, reset timer
2. Another message within 5s → add to buffer, reset timer
3. 5 seconds of silence → drain buffer, process all messages as a batch
4. If a response is already being generated, queue incoming messages for the next batch

### 2.7 Authorization

Only the configured user may interact with the bot.

| Parameter | Value |
|-----------|-------|
| Method | Chat ID allowlist |
| Config | `TELEGRAM_ALLOWED_CHAT_IDS` (comma-separated) |
| Unauthorized behavior | Silently ignore messages |

---

## 3. Technical Architecture

### 3.1 System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Compose                        │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │              buddy-bot (Python)                  │    │
│  │                                                  │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │    │
│  │  │ Telegram  │  │ Message  │  │  Anthropic   │  │    │
│  │  │ Handler   │──│ Buffer   │──│  API Client  │  │    │
│  │  └──────────┘  └──────────┘  └──────┬───────┘  │    │
│  │                                      │          │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────┴───────┐  │    │
│  │  │ History   │  │ Graphiti │  │    Tool      │  │    │
│  │  │ Store     │  │ Client   │  │   Registry   │  │    │
│  │  │ (SQLite)  │  │ (HTTP)   │  │              │  │    │
│  │  └──────────┘  └──────────┘  └──────────────┘  │    │
│  │       │              │                          │    │
│  │       ▼              │                          │    │
│  │  /data/history.db    │                          │    │
│  └──────────────────────│──────────────────────────┘    │
│                         │                               │
│  ┌──────────────────────▼──────────────────────────┐    │
│  │           graphiti-mcp (:8000)                   │    │
│  │  ┌─────────────┐  ┌─────────────────────────┐  │    │
│  │  │ FalkorDB    │  │ Graphiti Knowledge Graph │  │    │
│  │  │ (embedded)  │  │ (LLM: OpenAI, Embed:    │  │    │
│  │  │             │  │  Voyage-4)               │  │    │
│  │  └─────────────┘  └─────────────────────────┘  │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
└─────────────────────────────────────────────────────────┘
         │                           │
         ▼                           ▼
   Telegram Bot API            Anthropic API
   (webhooks/polling)          (Messages)
```

### 3.2 Component Overview

| Component | Responsibility |
|-----------|---------------|
| **Telegram Handler** | Receives messages via polling (or webhook), sends responses, manages typing indicators and emoji reactions |
| **Message Buffer** | Debounces rapid-fire messages into batches (5s trailing edge) |
| **Anthropic API Client** | Builds prompts, calls Claude Messages API with tools, streams responses |
| **Tool Registry** | Defines and dispatches tools (Graphiti memory, calendar, email, etc.) |
| **History Store** | SQLite-backed storage of raw conversation turns (last 20 turns) |
| **Graphiti Client** | HTTP client for the Graphiti MCP server (episodes, facts, nodes) |
| **graphiti-mcp** | Temporal knowledge graph server (separate container) |

### 3.3 Request Flow — Sequence Diagram

```
User          Telegram API      Bot                 Claude API       Graphiti
  │                │              │                      │              │
  │── message ────►│              │                      │              │
  │                │── webhook ──►│                      │              │
  │                │              │── react 👀 ─────────►│              │
  │                │              │── start typing ─────►│              │
  │                │              │                      │              │
  │                │              │   [debounce 5s]      │              │
  │                │              │                      │              │
  │                │              │── get_history() ────►│              │
  │                │              │◄─ last 20 turns ─────│              │
  │                │              │                      │              │
  │                │              │── build_prompt() ───►│              │
  │                │              │   Messages API       │              │
  │                │              │◄─ tool_use: ─────────│              │
  │                │              │   get_episodes       │              │
  │                │              │── get_episodes() ───►│─────────────►│
  │                │              │◄─ episodes ──────────│◄─────────────│
  │                │              │── tool_result ──────►│              │
  │                │              │◄─ tool_use: ─────────│              │
  │                │              │   search_facts       │              │
  │                │              │── search_facts() ───►│─────────────►│
  │                │              │◄─ facts ─────────────│◄─────────────│
  │                │              │── tool_result ──────►│              │
  │                │              │◄─ text response ─────│              │
  │                │              │◄─ tool_use: ─────────│              │
  │                │              │   add_memory         │              │
  │                │              │── add_memory() ─────►│─────────────►│
  │                │              │◄─ ok ────────────────│◄─────────────│
  │                │              │── tool_result ──────►│              │
  │                │              │◄─ end_turn ──────────│              │
  │                │              │                      │              │
  │                │              │── save_turn() (SQLite)              │
  │                │              │── stop typing ──────►│              │
  │                │◄─ message ───│                      │              │
  │◄── message ────│              │                      │              │
```

### 3.4 Concurrency Model

The bot runs as a single async Python process using `asyncio`:

- **Telegram polling/webhook**: async via `python-telegram-bot` library
- **Message buffer**: `asyncio.Event` for wake-up, same pattern as orca's `EventBuffer`
- **Claude API calls**: async HTTP via `httpx` (the `anthropic` SDK supports async natively)
- **Graphiti calls**: async HTTP via `httpx`
- **History store**: synchronous SQLite (fast, run in executor for non-blocking)
- **Serial processing**: Only one Claude API call at a time per chat (prevents race conditions)

---

## 4. Tool Specifications

Tools are defined using Claude's native tool_use format and passed to the Messages API.

### 4.1 Graphiti Memory Tools

These tools are called by Claude as part of the retrieval/save cycle. The bot intercepts `tool_use` blocks and executes them against the Graphiti HTTP API.

#### `get_episodes`

Retrieve recent episodes chronologically.

```json
{
  "name": "get_episodes",
  "description": "Retrieve the most recent conversation episodes from long-term memory. Use this at the start of every interaction to get recent context.",
  "input_schema": {
    "type": "object",
    "properties": {
      "group_ids": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Memory group IDs to search",
        "default": ["main"]
      },
      "max_episodes": {
        "type": "integer",
        "description": "Maximum number of episodes to retrieve",
        "default": 5
      }
    },
    "required": []
  }
}
```

**Implementation**: `GET {GRAPHITI_URL}/episodes?group_ids=main&max_episodes=5`

#### `search_memory_facts`

Semantic search over extracted facts and relationships.

```json
{
  "name": "search_memory_facts",
  "description": "Search long-term memory for facts and relationships. Use for finding pending tasks, user preferences, past decisions, or any specific topic.",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Natural language search query"
      },
      "group_ids": {
        "type": "array",
        "items": { "type": "string" },
        "default": ["main"]
      }
    },
    "required": ["query"]
  }
}
```

**Implementation**: `POST {GRAPHITI_URL}/search/facts` with `{"query": "...", "group_ids": [...]}`

#### `search_nodes`

Semantic search over entity nodes.

```json
{
  "name": "search_nodes",
  "description": "Search for entities (people, projects, topics) in long-term memory. Use when you need to know about a specific entity or topic.",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Entity or topic to search for"
      },
      "group_ids": {
        "type": "array",
        "items": { "type": "string" },
        "default": ["main"]
      }
    },
    "required": ["query"]
  }
}
```

**Implementation**: `POST {GRAPHITI_URL}/search/nodes` with `{"query": "...", "group_ids": [...]}`

#### `add_memory`

Save a new episode to long-term memory.

```json
{
  "name": "add_memory",
  "description": "Save a conversation summary to long-term memory. Call this after every interaction with a summary of: what the user said, what you responded, actions taken, and pending items.",
  "input_schema": {
    "type": "object",
    "properties": {
      "name": {
        "type": "string",
        "description": "Short descriptive name for this memory episode"
      },
      "episode_body": {
        "type": "string",
        "description": "Free-form text summary of the interaction"
      },
      "group_id": {
        "type": "string",
        "default": "main"
      },
      "source": {
        "type": "string",
        "default": "text"
      }
    },
    "required": ["name", "episode_body"]
  }
}
```

**Implementation**: `POST {GRAPHITI_URL}/episodes` with `{"name": "...", "episode_body": "...", "group_id": "main", "source": "text"}`

### 4.2 Google Calendar Tool

#### `calendar_list_events`

```json
{
  "name": "calendar_list_events",
  "description": "List upcoming events from the user's Google Calendar.",
  "input_schema": {
    "type": "object",
    "properties": {
      "days_ahead": {
        "type": "integer",
        "description": "Number of days to look ahead",
        "default": 7
      },
      "max_results": {
        "type": "integer",
        "default": 10
      }
    }
  }
}
```

**Implementation**: Google Calendar API v3 — `events.list()` with `timeMin=now`, `timeMax=now+days_ahead`.

#### `calendar_create_event`

```json
{
  "name": "calendar_create_event",
  "description": "Create a new event on the user's Google Calendar.",
  "input_schema": {
    "type": "object",
    "properties": {
      "summary": { "type": "string", "description": "Event title" },
      "start_time": { "type": "string", "description": "ISO 8601 start time" },
      "end_time": { "type": "string", "description": "ISO 8601 end time" },
      "description": { "type": "string", "description": "Event description" },
      "location": { "type": "string", "description": "Event location" }
    },
    "required": ["summary", "start_time", "end_time"]
  }
}
```

**Implementation**: Google Calendar API v3 — `events.insert()`.

#### `calendar_delete_event`

```json
{
  "name": "calendar_delete_event",
  "description": "Delete an event from the user's Google Calendar.",
  "input_schema": {
    "type": "object",
    "properties": {
      "event_id": { "type": "string", "description": "The calendar event ID to delete" }
    },
    "required": ["event_id"]
  }
}
```

### 4.3 Email Tool (Gmail)

#### `email_list_messages`

```json
{
  "name": "email_list_messages",
  "description": "List recent emails from the user's inbox.",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": { "type": "string", "description": "Gmail search query (e.g., 'is:unread', 'from:boss@company.com')", "default": "is:unread" },
      "max_results": { "type": "integer", "default": 10 }
    }
  }
}
```

**Implementation**: Gmail API — `messages.list()` with query, then `messages.get()` for each.

#### `email_read_message`

```json
{
  "name": "email_read_message",
  "description": "Read the full content of a specific email.",
  "input_schema": {
    "type": "object",
    "properties": {
      "message_id": { "type": "string", "description": "Gmail message ID" }
    },
    "required": ["message_id"]
  }
}
```

#### `email_send_message`

```json
{
  "name": "email_send_message",
  "description": "Send an email on behalf of the user. Always confirm with the user before sending.",
  "input_schema": {
    "type": "object",
    "properties": {
      "to": { "type": "string", "description": "Recipient email address" },
      "subject": { "type": "string" },
      "body": { "type": "string", "description": "Email body (plain text)" },
      "reply_to_message_id": { "type": "string", "description": "Message ID to reply to (optional)" }
    },
    "required": ["to", "subject", "body"]
  }
}
```

### 4.4 Utility Tools

#### `get_current_time`

```json
{
  "name": "get_current_time",
  "description": "Get the current date and time in the user's timezone.",
  "input_schema": {
    "type": "object",
    "properties": {
      "timezone": { "type": "string", "default": "UTC" }
    }
  }
}
```

#### `web_search`

```json
{
  "name": "web_search",
  "description": "Search the web for current information.",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": { "type": "string", "description": "Search query" }
    },
    "required": ["query"]
  }
}
```

**Implementation**: Tavily API, SerpAPI, or similar search API.

---

## 5. Data Model

### 5.1 Conversation History (SQLite)

```sql
-- Raw conversation turns for short-term exact-wording recall
CREATE TABLE turns (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     TEXT NOT NULL,
    user_text   TEXT NOT NULL,           -- User message(s), joined with newlines if batched
    bot_response TEXT NOT NULL,          -- Bot's response text
    duration_ms INTEGER,                 -- Response generation time
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_turns_chat_id ON turns(chat_id);
CREATE INDEX idx_turns_created_at ON turns(created_at);

-- Fallback context for retry after failure
CREATE TABLE fallback_context (
    chat_id     TEXT PRIMARY KEY,
    stdout      TEXT NOT NULL,           -- Last partial response
    updated_at  TEXT DEFAULT (datetime('now'))
);
```

### 5.2 Graphiti Knowledge Graph (Managed by Graphiti)

Graphiti manages its own data model internally. From the bot's perspective:

| Concept | Description | Managed By |
|---------|-------------|-----------|
| **Episodes** | Chronological conversation summaries (one per interaction) | Bot saves via `add_memory` |
| **Entity Nodes** | People, projects, topics, tools extracted from episodes | Graphiti LLM (automatic) |
| **Fact Edges** | Relationships between entities with temporal validity | Graphiti LLM (automatic) |
| **Embeddings** | 1024-dim Voyage-4 vectors for semantic search | Graphiti (automatic) |

**Group ID**: All data uses `group_id="main"` (single-user system).

### 5.3 Google OAuth Tokens (SQLite)

```sql
CREATE TABLE oauth_tokens (
    service     TEXT PRIMARY KEY,        -- 'google_calendar', 'gmail'
    token_json  TEXT NOT NULL,           -- Serialized OAuth2 credentials
    updated_at  TEXT DEFAULT (datetime('now'))
);
```

---

## 6. Deployment

### 6.1 Docker Compose Setup

```yaml
services:
  buddy-bot:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: buddy-bot
    restart: unless-stopped
    volumes:
      - bot_data:/data                    # SQLite databases
      - ./credentials:/app/credentials:ro  # Google OAuth credentials
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - TELEGRAM_TOKEN=${TELEGRAM_TOKEN}
      - TELEGRAM_ALLOWED_CHAT_IDS=${TELEGRAM_ALLOWED_CHAT_IDS}
      - GRAPHITI_URL=http://graphiti-mcp:8000
      - MODEL=${MODEL:-claude-sonnet-4-5-20250929}
      - HISTORY_TURNS=${HISTORY_TURNS:-20}
      - HISTORY_DB=/data/history.db
      - DEBOUNCE_DELAY=${DEBOUNCE_DELAY:-5}
      - USER_TIMEZONE=${USER_TIMEZONE:-UTC}
      - TAVILY_API_KEY=${TAVILY_API_KEY:-}
    networks:
      - bot-net
    depends_on:
      graphiti-mcp:
        condition: service_healthy

  graphiti-mcp:
    image: zepai/knowledge-graph-mcp:latest
    container_name: graphiti-mcp
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - graphiti_data:/data
      - ./config/graphiti-config.yaml:/app/mcp/config/config.yaml:ro
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - VOYAGE_API_KEY=${VOYAGE_API_KEY}
      - GRAPHITI_TELEMETRY_ENABLED=false
      - SEMAPHORE_LIMIT=10
    networks:
      - bot-net
    healthcheck:
      test: ["CMD-SHELL", "python3 -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/health')\" || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 30s

networks:
  bot-net:
    driver: bridge

volumes:
  bot_data:
  graphiti_data:
```

### 6.2 Bot Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

# Create data directory
RUN mkdir -p /data

CMD ["python", "-m", "buddy_bot.main"]
```

### 6.3 Graphiti Config

File: `config/graphiti-config.yaml`

```yaml
llm:
  provider: openai
  model: gpt-4.1-mini
  providers:
    openai:
      api_key: ${OPENAI_API_KEY}

embedder:
  provider: voyage
  model: voyage-4
  dimensions: 1024
  providers:
    voyage:
      api_key: ${VOYAGE_API_KEY}
```

---

## 7. Configuration

### 7.1 Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude | `sk-ant-...` |
| `TELEGRAM_TOKEN` | Telegram Bot token from @BotFather | `7123456789:AAH...` |
| `TELEGRAM_ALLOWED_CHAT_IDS` | Comma-separated authorized chat IDs | `123456789` |
| `OPENAI_API_KEY` | For Graphiti entity extraction (gpt-4.1-mini) | `sk-...` |
| `VOYAGE_API_KEY` | For Graphiti Voyage-4 embeddings | `pa-...` |

### 7.2 Optional Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL` | `claude-sonnet-4-5-20250929` | Claude model ID |
| `MAX_TOKENS` | `4096` | Max response tokens |
| `TEMPERATURE` | `0.7` | Claude temperature |
| `HISTORY_TURNS` | `20` | Number of conversation turns to include |
| `HISTORY_MAX_CHARS` | `500` | Max chars per turn in history |
| `HISTORY_DB` | `/data/history.db` | SQLite database path |
| `DEBOUNCE_DELAY` | `5` | Seconds to wait for more messages |
| `USER_TIMEZONE` | `UTC` | User's timezone for time-related tools |
| `GRAPHITI_URL` | `http://graphiti-mcp:8000` | Graphiti server URL |
| `TAVILY_API_KEY` | (empty) | Tavily API key for web search (optional tool) |
| `GOOGLE_CREDENTIALS_PATH` | `/app/credentials/google_credentials.json` | Google OAuth client credentials |
| `TELEGRAM_MODE` | `polling` | `polling` or `webhook` |
| `WEBHOOK_URL` | (empty) | Public URL for webhook mode |
| `WEBHOOK_PORT` | `8443` | Port for webhook server |
| `LOG_LEVEL` | `INFO` | Logging level |
| `FALLBACK_MAX_CHARS` | `4000` | Max chars for fallback context |

### 7.3 `.env.example`

```bash
# Required
ANTHROPIC_API_KEY=your_anthropic_api_key
TELEGRAM_TOKEN=your_bot_token
TELEGRAM_ALLOWED_CHAT_IDS=your_chat_id
OPENAI_API_KEY=sk-your_openai_api_key
VOYAGE_API_KEY=pa-your_voyage_api_key

# Optional
MODEL=claude-sonnet-4-5-20250929
HISTORY_TURNS=20
DEBOUNCE_DELAY=5
USER_TIMEZONE=America/New_York
TAVILY_API_KEY=tvly-your_key
TELEGRAM_MODE=polling
LOG_LEVEL=INFO
```

---

## 8. Error Handling & Edge Cases

### 8.1 Graphiti Unavailable

**Adapted from orca's soft health check pattern**

- Before each Claude API call, ping `{GRAPHITI_URL}/health`
- If unhealthy: log warning, proceed without memory context
- Claude sees no episodes/facts → treats as first conversation (prompt handles this)
- The prompt says: "If no episodes or facts are found, proceed without context"
- Memory tools return empty results rather than throwing errors

### 8.2 Claude API Failure

| Scenario | Handling |
|----------|---------|
| Rate limit (429) | Exponential backoff: 1s, 2s, 4s, max 3 retries |
| Server error (5xx) | Retry once after 2s |
| Timeout | 120s timeout, no retry |
| Overloaded (529) | Back off 30s, retry once |
| Invalid request (400) | Log error, send user a generic "something went wrong" |

On failure with partial response:
- Save partial stdout as fallback context (same pattern as orca's `_fallback_stdout`)
- Truncate to `FALLBACK_MAX_CHARS` (4000)
- Include in next prompt's Section 5

### 8.3 Message Processing Failure

If any error occurs during message processing:
- Re-queue the messages in the buffer (same pattern as orca's `_buffer.append(events)`)
- Wait `RETRY_DELAY` seconds (default 30s)
- Retry on next cycle
- After 3 consecutive failures for the same batch: drop messages, log error, send user "I'm having trouble right now, please try again later"

### 8.4 Telegram API Errors

| Error | Handling |
|-------|---------|
| Message too long (>4096 chars) | Split into multiple messages at paragraph boundaries |
| Chat not found | Log and skip (user may have blocked the bot) |
| Rate limit (429) | Respect `retry_after` from Telegram response |
| Network error | Retry with exponential backoff |

### 8.5 Typing Indicator Management

**Adapted from orca's `src/executor/typing.py`**

- Start sending `typing` action every 4 seconds when processing begins
- Cancel the typing loop when the response is sent
- If processing takes >120s, stop typing (Telegram shows it for max 5s per action)
- Typing indicator is fire-and-forget: failures are logged but don't affect processing

### 8.6 Concurrent Messages

- Only one Claude API call active per chat at a time
- Messages arriving during processing are queued in the buffer
- When current processing finishes, check buffer — if non-empty, drain and process immediately
- Same state machine as orca's Runner: IDLE → DEBOUNCE → DRAIN → PROCESS → CHECK BUFFER → IDLE

### 8.7 Episode Save Failure

**Adapted from orca's fallback pattern**

- If `add_memory` fails during a Claude tool call, the bot still has the text response
- The response is delivered to the user normally
- The fallback stdout mechanism captures what was said
- Next interaction includes fallback context so Claude knows what happened

---

## 9. Project Structure

```
buddy-bot/
├── src/
│   └── buddy_bot/
│       ├── __init__.py
│       ├── main.py                 # Entry point, starts bot + async loop
│       ├── config.py               # Environment variable loading
│       ├── bot.py                  # Telegram bot setup, handlers, authorization
│       ├── buffer.py               # Message buffer with debounce (from orca)
│       ├── processor.py            # Message processing pipeline (prompt → API → response)
│       ├── prompt.py               # Prompt assembly (from orca's build_prompt)
│       ├── history.py              # SQLite conversation history (from orca)
│       ├── graphiti.py             # Graphiti HTTP client
│       ├── typing_indicator.py     # Telegram typing indicator loop (from orca)
│       └── tools/
│           ├── __init__.py
│           ├── registry.py         # Tool definition and dispatch
│           ├── memory.py           # Graphiti memory tools (get_episodes, search, add)
│           ├── calendar.py         # Google Calendar tools
│           ├── email.py            # Gmail tools
│           ├── time.py             # Current time tool
│           └── search.py           # Web search tool
├── config/
│   └── graphiti-config.yaml        # Graphiti LLM/embedder config
├── credentials/                    # Google OAuth credentials (gitignored)
├── tests/
│   ├── __init__.py
│   ├── test_buffer.py
│   ├── test_processor.py
│   ├── test_prompt.py
│   ├── test_history.py
│   └── test_tools/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── .env.example
├── .gitignore
└── SPECIFICATION.md                # This document
```

### 9.1 Python Dependencies

```toml
[project]
name = "buddy-bot"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "anthropic>=0.40.0",
    "python-telegram-bot[webhooks]>=21.0",
    "httpx>=0.27.0",
    "pydantic>=2.0",
    "google-api-python-client>=2.0",
    "google-auth-httplib2>=0.2.0",
    "google-auth-oauthlib>=1.2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=5.0",
    "httpx>=0.27.0",
]
```

---

## 10. Implementation Notes

### 10.1 Key Patterns Borrowed from Orca

| Pattern | Orca Source | Buddy Bot Adaptation |
|---------|-------------|---------------------|
| Message buffer with debounce | `src/executor/buffer.py` | Same `asyncio.Event` pattern, shorter delay (5s vs 30s) |
| Prompt assembly | `src/executor/prompt.py` | Same 5-section structure, adapted for direct API use |
| Conversation history in SQLite | `src/executor/history.py` | Same schema, 20 turns instead of 10 |
| Typing indicator loop | `src/executor/typing.py` | Same async task pattern |
| Fallback stdout on failure | `src/executor/runner.py` | Same truncation and re-injection approach |
| Graphiti retrieval strategy | `specs/graphiti-memory-continuity.md` | Same 3-step retrieve + 1-step save |
| Serial execution per chat | `src/executor/runner.py` loop | Same state machine: IDLE → DEBOUNCE → PROCESS → CHECK |
| Soft health check on Graphiti | `src/executor/runner.py` | Same warn-and-proceed pattern |

### 10.2 Key Differences from Orca

| Aspect | Orca | Buddy Bot |
|--------|------|-----------|
| LLM invocation | `claude -p` CLI subprocess | Anthropic Messages API directly |
| Tool protocol | MCP (JSON-RPC over stdio/HTTP) | Claude native `tool_use` |
| Webhook routing | n8n workflow engine | Direct `python-telegram-bot` handlers |
| Architecture | 8 Docker services | 2 Docker services (bot + graphiti) |
| Use case | Software dev assistant with code tools | Personal assistant with calendar/email |
| Telegram delivery | n8n callback → Telegram API | Direct `bot.send_message()` |
| Progress messages | MCP tool call detection → Telegram | Tool call detection in streaming → Telegram |

### 10.3 Google OAuth Setup (One-Time)

1. Create a Google Cloud project and enable Calendar API + Gmail API
2. Create OAuth 2.0 credentials (Desktop application type)
3. Download `credentials.json` to `credentials/google_credentials.json`
4. Run the bot locally once — it will open a browser for OAuth consent
5. Token is saved to SQLite and auto-refreshed

### 10.4 Telegram Bot Setup

1. Message @BotFather on Telegram, create a new bot, get the token
2. Message @userinfobot to get your chat ID
3. Set `TELEGRAM_TOKEN` and `TELEGRAM_ALLOWED_CHAT_IDS` in `.env`
4. For webhook mode on a server: set `TELEGRAM_MODE=webhook` and `WEBHOOK_URL=https://your-domain.com`

---

## Appendix A: Graphiti API Reference

The bot communicates with Graphiti over HTTP. The actual Graphiti MCP server exposes these endpoints (mapped from MCP tool calls):

| Operation | HTTP Method | Endpoint | Body |
|-----------|-------------|----------|------|
| Get episodes | POST | `/mcp/` | MCP JSON-RPC: `tools/call` with `get_episodes` |
| Search facts | POST | `/mcp/` | MCP JSON-RPC: `tools/call` with `search_memory_facts` |
| Search nodes | POST | `/mcp/` | MCP JSON-RPC: `tools/call` with `search_nodes` |
| Add memory | POST | `/mcp/` | MCP JSON-RPC: `tools/call` with `add_memory` |
| Health check | GET | `/health` | — |

**Note**: The Graphiti MCP server uses JSON-RPC over HTTP. The bot's `graphiti.py` client wraps these into simple async methods. Alternatively, use the `graphiti-core` Python SDK directly if a simpler HTTP interface is preferred over MCP JSON-RPC.

## Appendix B: Message Format Reference

### Telegram Update (incoming)

```json
{
  "update_id": 987654321,
  "message": {
    "message_id": 42,
    "from": {
      "id": 123456789,
      "first_name": "Alex",
      "username": "alex"
    },
    "chat": {
      "id": 123456789,
      "type": "private"
    },
    "date": 1706900000,
    "text": "remind me to review the PR tomorrow"
  }
}
```

### Event Batch (internal, passed to prompt builder)

```json
[
  {
    "text": "remind me to review the PR tomorrow",
    "from": "alex",
    "chat_id": "123456789",
    "message_id": 42,
    "timestamp": "2026-02-10T14:30:00Z"
  }
]
```

### Claude Messages API Request (simplified)

```json
{
  "model": "claude-sonnet-4-5-20250929",
  "max_tokens": 4096,
  "system": "<Section 1: System Context>",
  "messages": [
    {
      "role": "user",
      "content": "<Section 2 + 3 + 4 + 5 assembled>"
    }
  ],
  "tools": [
    { "name": "get_episodes", "..." },
    { "name": "search_memory_facts", "..." },
    { "name": "add_memory", "..." },
    { "name": "calendar_list_events", "..." },
    { "name": "email_list_messages", "..." }
  ]
}
```

### Tool Use Cycle

```json
// Claude responds with tool_use
{
  "role": "assistant",
  "content": [
    {
      "type": "tool_use",
      "id": "toolu_abc123",
      "name": "get_episodes",
      "input": { "group_ids": ["main"], "max_episodes": 5 }
    }
  ]
}

// Bot executes tool, sends result back
{
  "role": "user",
  "content": [
    {
      "type": "tool_result",
      "tool_use_id": "toolu_abc123",
      "content": "[{\"name\": \"PR discussion\", \"body\": \"User asked about PR status...\"}]"
    }
  ]
}

// Claude may call more tools or produce final text response
{
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "Got it! I'll remind you to review the PR tomorrow."
    }
  ]
}
```
