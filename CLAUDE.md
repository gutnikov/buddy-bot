# Buddy Bot

Telegram personal assistant powered by Claude Code CLI + Graphiti knowledge graph memory.

## Architecture

- Telegram bot (python-telegram-bot) → message buffer (debounce) → Claude CLI executor (`claude -p` subprocess)
- MCP server (`python -m buddy_bot.mcp_server`) exposes tools to Claude via stdio — runs as subprocess, not imported by bot
- Graphiti MCP provides long-term memory (episodes, facts, entities)
- Conversation history in SQLite (`/data/history.db`)

## Commands

- `PYTHONPATH=src pytest tests/ -v` — run tests locally (editable install broken on Python 3.10)
- `PYTHONPATH=src pytest tests/ -v -m "not docker"` — run tests excluding Docker integration tests
- `make test` — run tests via Docker (falls back to local)
- `make setup-hooks` — install git pre-commit hook (ruff linting)
- `docker compose up -d` — start bot + graphiti-mcp
- `make render-env` — render .env from SOPS-encrypted secrets

## Linting

- ruff with rules: E, F, I, W, UP, B, SIM (line-length=120, E501 ignored)
- `ruff check src/ tests/` — lint all code
- `ruff check --fix src/ tests/` — auto-fix violations
- Pre-commit hook in `.githooks/pre-commit` — runs ruff on staged .py files
- CI runs lint step before tests

## Testing

- pytest-asyncio with `asyncio_mode = "auto"`
- SQLite in-memory databases for store tests
- Docker tests marked with `@pytest.mark.docker` — excluded from CI, run locally only
- CI workflow: `.gitea/workflows/test.yaml` — lint then `pytest -m "not docker"`

## Gitea

- Remote: ssh://git@92.118.232.241:2222/alex/buddy-bot.git
- API: http://92.118.232.241:3000/api/v1/ (use $GITEA_TOKEN)
- No `gh` CLI — use `curl` with Gitea API or `tea` CLI
- Branch protection on main requires CI status check "Tests / test (pull_request)"
