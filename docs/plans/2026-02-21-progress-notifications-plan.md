# Progress Notifications Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `notify_progress` MCP tool so Claude can send intermediate progress messages to the user's Telegram chat during processing.

**Architecture:** The MCP server gets a new `notify_progress` tool that calls the Telegram Bot API directly via `urllib.request`. Claude decides what/when to send. The prompt is updated with usage guidelines.

**Tech Stack:** Python stdlib (`urllib.request`, `json`), MCP SDK, pytest with `unittest.mock`

---

### Task 1: Add `notify_progress` tool to MCP server

**Files:**
- Modify: `src/buddy_bot/mcp_server.py:22-66`
- Test: `tests/test_mcp_server.py`

**Step 1: Write the failing tests**

Add to `tests/test_mcp_server.py`:

```python
async def test_notify_progress_success(monkeypatch):
    """notify_progress sends message via Telegram API and returns success."""
    from unittest.mock import MagicMock, patch
    from buddy_bot.mcp_server import _handle_notify_progress

    monkeypatch.setenv("TELEGRAM_TOKEN", "fake-token")
    import buddy_bot.mcp_server as mod
    mod.TELEGRAM_TOKEN = "fake-token"

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = b'{"ok":true}'
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("buddy_bot.mcp_server.urlopen", return_value=mock_response) as mock_urlopen:
        result = json.loads(await _handle_notify_progress({
            "chat_id": "123",
            "message": "On it!",
        }))

    assert result["status"] == "sent"
    mock_urlopen.assert_called_once()
    call_args = mock_urlopen.call_args
    req = call_args[0][0]
    assert "api.telegram.org" in req.full_url
    assert b"On it!" in req.data


async def test_notify_progress_missing_token(monkeypatch):
    """notify_progress returns error when TELEGRAM_TOKEN is not set."""
    from buddy_bot.mcp_server import _handle_notify_progress
    import buddy_bot.mcp_server as mod
    mod.TELEGRAM_TOKEN = ""

    result = json.loads(await _handle_notify_progress({
        "chat_id": "123",
        "message": "Hello",
    }))
    assert "error" in result


async def test_notify_progress_missing_params():
    """notify_progress returns error for missing required params."""
    from buddy_bot.mcp_server import _handle_notify_progress
    import buddy_bot.mcp_server as mod
    mod.TELEGRAM_TOKEN = "fake-token"

    result = json.loads(await _handle_notify_progress({}))
    assert "error" in result


async def test_notify_progress_http_failure(monkeypatch):
    """notify_progress returns error on HTTP failure."""
    from unittest.mock import patch
    from urllib.error import URLError
    from buddy_bot.mcp_server import _handle_notify_progress
    import buddy_bot.mcp_server as mod
    mod.TELEGRAM_TOKEN = "fake-token"

    with patch("buddy_bot.mcp_server.urlopen", side_effect=URLError("fail")):
        result = json.loads(await _handle_notify_progress({
            "chat_id": "123",
            "message": "test",
        }))
    assert "error" in result
```

Also update existing count-based tests:

```python
def test_tool_list():
    """Tools should include get_current_time and notify_progress."""
    from buddy_bot.mcp_server import TOOLS
    assert len(TOOLS) == 2
    names = [t.name for t in TOOLS]
    assert "get_current_time" in names
    assert "notify_progress" in names


async def test_list_tools_returns_all():
    """list_tools() returns 2 tools."""
    from buddy_bot.mcp_server import list_tools
    tools = await list_tools()
    assert len(tools) == 2
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src pytest tests/test_mcp_server.py -v`
Expected: FAIL — `_handle_notify_progress` not defined, count assertions wrong

**Step 3: Implement `notify_progress` in MCP server**

In `src/buddy_bot/mcp_server.py`, add after line 9 (`import os`):

```python
from urllib.request import Request, urlopen
from urllib.error import URLError
```

After line 22 (`USER_TIMEZONE = ...`), add:

```python
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
```

Add the tool definition to `TOOLS` list (after the `get_current_time` tool, before line 38's `]`):

```python
    Tool(
        name="notify_progress",
        description=(
            "Send a short progress message to the user's Telegram chat. "
            "Use this to acknowledge receipt or signal progress during long operations. "
            "Keep messages short (a few words). Don't overuse — 1-2 per interaction."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "chat_id": {
                    "type": "string",
                    "description": "The user's chat_id (provided in your prompt context).",
                },
                "message": {
                    "type": "string",
                    "description": "Short progress message, e.g. 'On it!' or 'Almost done!'",
                },
            },
            "required": ["chat_id", "message"],
        },
    ),
```

Add the handler function after `_handle_get_current_time` (after line 58):

```python
async def _handle_notify_progress(arguments: dict) -> str:
    """Send a progress message to the user via Telegram Bot API."""
    chat_id = arguments.get("chat_id", "")
    message = arguments.get("message", "")

    if not chat_id or not message:
        return json.dumps({"error": "chat_id and message are required"})

    token = TELEGRAM_TOKEN
    if not token:
        return json.dumps({"error": "TELEGRAM_TOKEN not configured"})

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": message}).encode()
    req = Request(url, data=payload, headers={"Content-Type": "application/json"})

    try:
        with urlopen(req, timeout=10) as resp:
            resp.read()
        return json.dumps({"status": "sent"})
    except (URLError, OSError) as exc:
        logger.warning("notify_progress failed for chat %s: %s", chat_id, exc)
        return json.dumps({"error": f"Failed to send: {exc}"})
```

Add to the `HANDLERS` dispatch table:

```python
HANDLERS: dict[str, object] = {
    "get_current_time": _handle_get_current_time,
    "notify_progress": _handle_notify_progress,
}
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src pytest tests/test_mcp_server.py -v`
Expected: all PASS

**Step 5: Run linter**

Run: `ruff check src/buddy_bot/mcp_server.py tests/test_mcp_server.py`
Expected: clean

**Step 6: Commit**

```bash
git add src/buddy_bot/mcp_server.py tests/test_mcp_server.py
git commit -m "feat: add notify_progress MCP tool for Telegram progress messages"
```

---

### Task 2: Update prompt with `notify_progress` usage guidelines

**Files:**
- Modify: `src/buddy_bot/prompt.py:9-23` (SYSTEM_CONTEXT)
- Test: `tests/test_prompt.py`

**Step 1: Write the failing test**

Add to `tests/test_prompt.py`:

```python
def test_prompt_contains_progress_instructions():
    """Prompt should mention notify_progress tool."""
    prompt = build_prompt(
        chat_id="123",
        history_turns=[],
        events=[{"text": "hello", "from": "alex", "timestamp": "t"}],
    )
    assert "notify_progress" in prompt
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_prompt.py::test_prompt_contains_progress_instructions -v`
Expected: FAIL — "notify_progress" not in prompt

**Step 3: Update SYSTEM_CONTEXT in prompt.py**

In `src/buddy_bot/prompt.py`, append to the `SYSTEM_CONTEXT` string (before the closing `"""`), after the line about MCP tools:

```python
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
- Do NOT use any file, bash, or code-editing tools. Only use MCP tools.

PROGRESS NOTIFICATIONS:
- Call notify_progress(chat_id, message) to send the user a short status update.
- Use it right after receiving a message to acknowledge ("On it!") and optionally
  during long operations ("Searching my memory...").
- Keep messages short — a few words. 1-2 progress messages per interaction is typical.
- The chat_id is provided below in your context."""
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_prompt.py -v`
Expected: all PASS

**Step 5: Run linter**

Run: `ruff check src/buddy_bot/prompt.py tests/test_prompt.py`
Expected: clean

**Step 6: Commit**

```bash
git add src/buddy_bot/prompt.py tests/test_prompt.py
git commit -m "feat: add notify_progress usage guidelines to prompt"
```

---

### Task 3: Update progress.py mapping and final verification

**Files:**
- Modify: `src/buddy_bot/progress.py:4-12`

**Step 1: Add notify_progress to the progress mapping**

In `src/buddy_bot/progress.py`, add entry to `TOOL_PROGRESS`:

```python
TOOL_PROGRESS: dict[str, str] = {
    # Memory tools (via Graphiti MCP)
    "get_episodes": "Recalling recent conversations...",
    "search_memory_facts": "Searching memory...",
    "search_nodes": "Looking up entities...",
    "add_memory": "Saving to memory...",
    # Time
    "get_current_time": "Checking the time...",
    # Progress
    "notify_progress": "Sending progress update...",
}
```

**Step 2: Run full test suite**

Run: `PYTHONPATH=src pytest tests/ -v -m "not docker"`
Expected: all PASS

**Step 3: Run full lint**

Run: `ruff check src/ tests/`
Expected: clean

**Step 4: Commit**

```bash
git add src/buddy_bot/progress.py
git commit -m "feat: add notify_progress to tool progress mapping"
```
