"""Message buffer with trailing-edge debounce."""

import asyncio
import logging

logger = logging.getLogger(__name__)


class MessageBuffer:
    def __init__(self, debounce_delay: float = 5.0) -> None:
        self._debounce_delay = debounce_delay
        self._events: list[dict] = []
        self._event = asyncio.Event()
        self._lock = asyncio.Lock()

    def add(self, event: dict) -> None:
        self._events.append(event)
        self._event.set()

    async def wait_and_drain(self) -> list[dict]:
        """Wait for debounce silence, then drain and return all buffered events."""
        # Wait until there's at least one event
        await self._event.wait()

        # Trailing-edge debounce: keep waiting while new messages arrive
        while True:
            self._event.clear()
            try:
                await asyncio.wait_for(self._event.wait(), timeout=self._debounce_delay)
                # New event arrived within debounce window, loop again
            except asyncio.TimeoutError:
                # Silence period elapsed, drain the buffer
                break

        async with self._lock:
            events = self._events[:]
            self._events.clear()
            self._event.clear()
            return events

    def is_empty(self) -> bool:
        return len(self._events) == 0

    def append(self, events: list[dict]) -> None:
        """Re-queue events (for retry on failure)."""
        self._events.extend(events)
        if events:
            self._event.set()
