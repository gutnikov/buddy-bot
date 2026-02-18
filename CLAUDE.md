# Buddy Bot

Telegram personal assistant powered by Claude Code CLI + Graphiti knowledge graph memory.

## Architecture

- Telegram bot (python-telegram-bot) → message buffer (debounce) → Claude CLI executor (`claude -p` subprocess)
- MCP server (`python -m buddy_bot.mcp_server`) exposes tools to Claude via stdio — runs as subprocess, not imported by bot
- Graphiti MCP provides long-term memory (episodes, facts, entities)
- Conversation history in SQLite (`/data/history.db`)

## Commands

- `PYTHONPATH=src pytest tests/ -v` — run tests locally (editable install broken on Python 3.10)
- `make test` — run tests via Docker (falls back to local)
- `docker compose up -d` — start bot + graphiti-mcp
- `make render-env` — render .env from SOPS-encrypted secrets

## Testing

- pytest-asyncio with `asyncio_mode = "auto"`
- SQLite in-memory databases for store tests
- `test_docker.py::test_image_size_under_500mb` is a known pre-existing failure (773MB > 500MB)

## Gitea

- Remote: ssh://git@92.118.232.241:2222/alex/buddy-bot.git
- API: http://92.118.232.241:3000/api/v1/ (use $GITEA_TOKEN)
- No `gh` CLI — use `curl` with Gitea API or `tea` CLI
