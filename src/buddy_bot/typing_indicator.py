"""Async Telegram 'typing...' action loop."""

import asyncio
import logging

from telegram.constants import ChatAction

logger = logging.getLogger(__name__)

TYPING_INTERVAL = 4.0
MAX_TYPING_DURATION = 120.0


class TypingIndicator:
    def __init__(self, bot, chat_id: str) -> None:
        self._bot = bot
        self._chat_id = int(chat_id)
        self._task: asyncio.Task | None = None

    async def _loop(self) -> None:
        elapsed = 0.0
        try:
            while elapsed < MAX_TYPING_DURATION:
                try:
                    await self._bot.send_chat_action(
                        chat_id=self._chat_id, action=ChatAction.TYPING
                    )
                except Exception:
                    logger.debug("Typing indicator send failed for chat %d", self._chat_id)
                await asyncio.sleep(TYPING_INTERVAL)
                elapsed += TYPING_INTERVAL
        except asyncio.CancelledError:
            return

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def __aenter__(self) -> "TypingIndicator":
        await self.start()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.stop()
