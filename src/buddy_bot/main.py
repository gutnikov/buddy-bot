"""Buddy Bot entry point — wires all components and starts the bot."""

import asyncio
import logging
import signal

import httpx

from buddy_bot.buffer import MessageBuffer
from buddy_bot.config import get_settings
from buddy_bot.graphiti import GraphitiClient
from buddy_bot.history import HistoryStore
from buddy_bot.processor import MessageProcessor
from buddy_bot.todo import TodoStore
from buddy_bot.tools.memory import register_memory_tools
from buddy_bot.tools.perplexity import register_perplexity_tool
from buddy_bot.tools.registry import ToolRegistry
from buddy_bot.tools.search import register_search_tool
from buddy_bot.tools.time import register_time_tool
from buddy_bot.tools.todo import register_todo_tools

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
        self._graphiti = GraphitiClient(self._settings.graphiti_url)
        self._todo = TodoStore(self._settings.history_db)
        self._http_client = httpx.AsyncClient()
        self._chat_id_ref: dict[str, str] = {}
        self._registry = ToolRegistry()
        self._register_tools()

    def _register_tools(self) -> None:
        register_memory_tools(self._registry, self._graphiti)
        register_time_tool(self._registry, self._settings.user_timezone)
        register_search_tool(self._registry, self._settings.tavily_api_key)
        register_perplexity_tool(self._registry, self._settings.perplexity_api_key)
        register_todo_tools(self._registry, self._todo, self._chat_id_ref)

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
                self._chat_id_ref["chat_id"] = chat_id
                await self._processor.process(chat_id, events)
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

        # Health check Graphiti
        if await self._graphiti.health_check():
            logger.info("Graphiti is healthy")
        else:
            logger.warning("Graphiti is not reachable — proceeding without memory")

        # Create Telegram application
        from buddy_bot.bot import create_application

        self._app = create_application(
            self._settings.telegram_token,
            self._settings.telegram_allowed_chat_ids,
            self.on_message,
            http_client=self._http_client,
            settings=self._settings,
        )

        # Create processor (needs the bot instance)
        self._processor = MessageProcessor(
            self._settings,
            self._history,
            self._registry,
            self._app.bot,
            graphiti=self._graphiti,
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
        if hasattr(self, "_processor"):
            await self._processor.close()
        await self._http_client.aclose()
        await self._graphiti.close()
        self._todo.close()
        self._history.close()

        logger.info("Shutdown complete")


def main() -> None:
    bot = BuddyBot()
    asyncio.run(bot.start())


if __name__ == "__main__":
    main()
