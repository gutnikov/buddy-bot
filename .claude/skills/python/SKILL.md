---
name: python
description: Writes production-ready Python code following best practices for type safety, error handling, testing, async patterns, and clean architecture. Use when writing new Python modules, functions, classes, or scripts that need to be robust and maintainable.
argument-hint: [description of what to build]
user-invocable: true
---

# Python — Production-Ready Code

Write production-ready Python 3.12+ code for: **$ARGUMENTS**

## Core Principles

1. **Type everything** — All function signatures must have full type hints (params + return). Use modern syntax: `str | None`, `list[str]`, `dict[str, Any]`. Use `TypeVar`, `Protocol`, `TypeAlias` where they add clarity.

2. **Fail explicitly** — Never swallow exceptions. Catch specific exceptions, log context, re-raise or convert to domain errors. Use custom exception hierarchies for library code.

3. **Validate at boundaries** — Use Pydantic models for external input (API payloads, config, file parsing). Trust internal code — don't over-validate between your own functions.

4. **Async by default for I/O** — Use `async def` for anything that touches network, disk, or subprocesses. Never call blocking I/O inside async functions without `asyncio.to_thread()`.

5. **Keep it simple** — No premature abstractions. Three similar lines beats a clever helper nobody asked for. Only add indirection when there's a concrete second use case.

## Code Structure

### Module layout

```
module/
├── __init__.py        # Public API re-exports only
├── models.py          # Pydantic data models
├── service.py         # Business logic
├── errors.py          # Custom exceptions (if needed)
└── _internal.py       # Private helpers (underscore prefix)
```

### Function design

- Single responsibility — one function does one thing
- Max ~30 lines per function; if longer, extract a helper with a clear name
- Positional args for required params, keyword-only (`*,`) for optional/config params
- Return early to reduce nesting

### Class design

- Prefer plain functions and modules over classes unless you need state
- Use `dataclass` or Pydantic `BaseModel` for data containers
- Use `Protocol` for duck-typed interfaces instead of ABC when possible
- Keep `__init__` thin — no I/O, no heavy computation

## Patterns to Follow

### Error handling

```python
class ServiceError(Exception):
    """Base for this module's errors."""

class NotFoundError(ServiceError):
    def __init__(self, resource: str, id: str) -> None:
        super().__init__(f"{resource} {id} not found")
        self.resource = resource
        self.id = id
```

### Logging (structlog)

```python
import structlog
logger = structlog.get_logger()

async def process(item_id: str) -> Result:
    logger.info("processing_started", item_id=item_id)
    try:
        result = await _do_work(item_id)
        logger.info("processing_completed", item_id=item_id)
        return result
    except ExternalAPIError as exc:
        logger.error("processing_failed", item_id=item_id, error=str(exc))
        raise ServiceError(f"Failed to process {item_id}") from exc
```

### Async context managers for resources

```python
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

@asynccontextmanager
async def managed_connection(url: str) -> AsyncIterator[Connection]:
    conn = await connect(url)
    try:
        yield conn
    finally:
        await conn.close()
```

### Configuration via pydantic-settings

```python
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    model_config = {"env_prefix": "APP_"}

    database_url: str
    debug: bool = False
    max_retries: int = Field(default=3, ge=1, le=10)
```

## Things to Avoid

- **Don't** use `Any` as a crutch — find the real type or use a `Protocol`
- **Don't** use mutable default arguments (`def f(items=[])`)
- **Don't** use bare `except:` or `except Exception:` without re-raising
- **Don't** use `os.system()` or `subprocess.run(shell=True)` — use `subprocess.run()` with a list and `shlex.quote()` for user input
- **Don't** use `print()` for application logging — use structlog
- **Don't** import everything with `from module import *`
- **Don't** write docstrings that just restate the function name — only add them when they provide non-obvious context
- **Don't** add `# type: ignore` without a specific error code

## Testing

When the task includes writing tests or the code is complex enough to warrant them:

- Use `pytest` with `async` support (`pytest-asyncio`)
- Name test files `test_<module>.py`, test functions `test_<behavior>()`
- Structure tests as Arrange/Act/Assert
- Use `tmp_path` for file system tests, `monkeypatch` for env vars
- Mock at the boundary (HTTP calls, DB queries), not internal functions
- Test behavior, not implementation — assert on outcomes, not call counts

## Checklist Before Finishing

- [ ] All functions have type hints (params + return)
- [ ] No bare exceptions, no swallowed errors
- [ ] Async used for all I/O operations
- [ ] Pydantic models for external data boundaries
- [ ] structlog for logging (not print, not stdlib logging)
- [ ] No security issues (injection, secrets in code, unsafe deserialization)
- [ ] Imports organized: stdlib → third-party → local, blank lines between
