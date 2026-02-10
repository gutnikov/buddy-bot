"""Tests for buddy_bot.retry module."""

import pytest

from buddy_bot.retry import MaxRetriesExceeded, retry_with_backoff


async def test_successful_call():
    async def ok():
        return 42

    result = await retry_with_backoff(ok, max_retries=3, backoff_base=0.01)
    assert result == 42


async def test_successful_retry():
    attempts = []

    async def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise ValueError("not yet")
        return "ok"

    result = await retry_with_backoff(
        flaky, max_retries=3, backoff_base=0.01
    )
    assert result == "ok"
    assert len(attempts) == 3


async def test_exceeds_max_retries():
    async def always_fail():
        raise ValueError("boom")

    with pytest.raises(MaxRetriesExceeded) as exc_info:
        await retry_with_backoff(
            always_fail, max_retries=2, backoff_base=0.01
        )
    assert exc_info.value.attempts == 3
    assert isinstance(exc_info.value.last_error, ValueError)


async def test_non_retriable_raises_immediately():
    attempts = []

    async def fail():
        attempts.append(1)
        raise TypeError("bad type")

    with pytest.raises(TypeError):
        await retry_with_backoff(
            fail,
            max_retries=3,
            backoff_base=0.01,
            retriable=lambda e: isinstance(e, ValueError),
        )
    assert len(attempts) == 1


async def test_backoff_max_caps_delay(monkeypatch):
    """Verify backoff_max is respected (indirectly via fast execution)."""
    attempts = []

    async def flaky():
        attempts.append(1)
        if len(attempts) < 2:
            raise ValueError("retry")
        return "done"

    result = await retry_with_backoff(
        flaky, max_retries=2, backoff_base=0.01, backoff_max=0.02
    )
    assert result == "done"


async def test_passes_args_and_kwargs():
    async def add(a, b, extra=0):
        return a + b + extra

    result = await retry_with_backoff(
        add, 1, 2, extra=10, max_retries=0, backoff_base=0.01
    )
    assert result == 13


async def test_zero_retries_no_retry():
    attempts = []

    async def fail():
        attempts.append(1)
        raise ValueError("no retries")

    with pytest.raises(MaxRetriesExceeded):
        await retry_with_backoff(fail, max_retries=0, backoff_base=0.01)
    assert len(attempts) == 1
