"""Buddy Bot entry point — wires all components and starts the bot."""

import asyncio
import logging
import signal

import httpx

from buddy_bot.buffer import MessageBuffer
from buddy_bot.config import get_settings
from buddy_bot.executor import ClaudeExecutor
from buddy_bot.history import HistoryStore

logger = logging.getLogger(__name__)


class BuddyBot:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._buffers: dict[str, MessageBuffer] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._shutdown_event = asyncio.Event()

        # Configure logging
        logging.basicConfig(
            level=getattr(logging, self._settings.log_level, logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            force=True,
        )

        # Initialize components
        self._history = HistoryStore(
            self._settings.history_db,
            max_chars=self._settings.history_max_chars,
        )
        self._http_client = httpx.AsyncClient()

    def _get_buffer(self, chat_id: str) -> MessageBuffer:
        if chat_id not in self._buffers:
            self._buffers[chat_id] = MessageBuffer(
                debounce_delay=float(self._settings.debounce_delay)
            )
        return self._buffers[chat_id]

    async def on_message(self, event: dict) -> None:
        """Called by the Telegram handler when a message is received."""
        chat_id = event["chat_id"]
        buf = self._get_buffer(chat_id)
        buf.add(event)

        # Start processing loop for this chat if not already running
        if chat_id not in self._tasks or self._tasks[chat_id].done():
            self._tasks[chat_id] = asyncio.create_task(
                self._processing_loop(chat_id)
            )

    async def _processing_loop(self, chat_id: str) -> None:
        """State machine: IDLE → DEBOUNCE → DRAIN → PROCESS → CHECK BUFFER → IDLE."""
        buf = self._get_buffer(chat_id)
        consecutive_failures = 0

        while not buf.is_empty() or not self._shutdown_event.is_set():
            events = await buf.wait_and_drain()
            if not events:
                break

            try:
                await self._executor.process(chat_id, events)
                consecutive_failures = 0
            except Exception:
                consecutive_failures += 1
                logger.exception(
                    "Processing failed (attempt %d) for chat %s",
                    consecutive_failures,
                    chat_id,
                )
                if consecutive_failures >= 3:
                    logger.error(
                        "Dropping messages after 3 failures for chat %s", chat_id
                    )
                    try:
                        from buddy_bot.bot import send_response

                        await send_response(
                            self._app.bot,
                            chat_id,
                            "I'm having trouble right now, please try again later.",
                        )
                    except Exception:
                        pass
                    break
                else:
                    buf.append(events)
                    await asyncio.sleep(30)

            # Check if more messages arrived during processing
            if buf.is_empty():
                break

    async def start(self) -> None:
        """Start the bot."""
        logger.info("Buddy Bot starting...")

        # Create Telegram application
        from buddy_bot.bot import create_application

        self._app = create_application(
            self._settings.telegram_token,
            self._settings.telegram_allowed_chat_ids,
            self.on_message,
            http_client=self._http_client,
            settings=self._settings,
        )

        # Create executor (needs the bot instance)
        self._executor = ClaudeExecutor(
            self._settings,
            self._history,
            self._app.bot,
        )

        # Set up signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))

        # Start polling
        logger.info("Starting Telegram polling...")
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()

        # Wait for shutdown
        await self._shutdown_event.wait()

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("Shutting down...")
        self._shutdown_event.set()

        # Stop Telegram
        if hasattr(self, "_app"):
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

        # Close clients
        if hasattr(self, "_executor"):
            await self._executor.close()
        await self._http_client.aclose()
        self._history.close()

        logger.info("Shutdown complete")


def main() -> None:
    bot = BuddyBot()
    asyncio.run(bot.start())


if __name__ == "__main__":
    main()
