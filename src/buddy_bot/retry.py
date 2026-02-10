"""Generic async retry utility with exponential backoff."""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class MaxRetriesExceeded(Exception):
    """Raised when all retry attempts are exhausted."""

    def __init__(self, last_error: Exception, attempts: int) -> None:
        self.last_error = last_error
        self.attempts = attempts
        super().__init__(f"Failed after {attempts} attempts: {last_error}")


async def retry_with_backoff(
    fn: Callable[..., Coroutine[Any, Any, T]],
    *args: Any,
    max_retries: int = 3,
    backoff_base: float = 1.0,
    backoff_max: float = 60.0,
    retriable: Callable[[Exception], bool] | None = None,
    **kwargs: Any,
) -> T:
    """Call an async function with exponential backoff on retriable errors.

    Args:
        fn: Async function to call.
        *args: Positional arguments for fn.
        max_retries: Maximum number of retry attempts (0 = no retries).
        backoff_base: Base delay in seconds (doubles each retry).
        backoff_max: Maximum delay cap in seconds.
        retriable: Predicate returning True if the error is retriable.
                   Defaults to retrying all exceptions.
        **kwargs: Keyword arguments for fn.

    Returns:
        The return value of fn.

    Raises:
        MaxRetriesExceeded: If all retries are exhausted.
        Exception: If a non-retriable error occurs.
    """
    if retriable is None:
        retriable = lambda _: True  # noqa: E731

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await fn(*args, **kwargs)
        except Exception as exc:
            last_error = exc
            if not retriable(exc):
                raise
            if attempt >= max_retries:
                raise MaxRetriesExceeded(exc, attempt + 1) from exc
            delay = min(backoff_base * (2**attempt), backoff_max)
            logger.warning(
                "Attempt %d/%d failed (%s), retrying in %.1fs",
                attempt + 1,
                max_retries + 1,
                type(exc).__name__,
                delay,
            )
            await asyncio.sleep(delay)

    # Should not reach here, but satisfy type checker
    assert last_error is not None
    raise MaxRetriesExceeded(last_error, max_retries + 1)
