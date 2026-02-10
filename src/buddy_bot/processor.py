"""Message processing pipeline: prompt → Claude API → tool loop → response."""

import asyncio
import logging
from datetime import datetime, timezone

import anthropic

from buddy_bot.bot import send_response
from buddy_bot.config import Settings
from buddy_bot.history import HistoryStore
from buddy_bot.prompt import build_system_prompt, build_user_prompt
from buddy_bot.tools.registry import ToolRegistry
from buddy_bot.typing_indicator import TypingIndicator

logger = logging.getLogger(__name__)

# Retry configuration
RETRY_DELAYS = [1, 2, 4]  # seconds for 429 retries
OVERLOADED_DELAY = 30
MAX_TOOL_ROUNDS = 20


class MessageProcessor:
    def __init__(
        self,
        settings: Settings,
        history_store: HistoryStore,
        tool_registry: ToolRegistry,
        bot,
    ) -> None:
        self._settings = settings
        self._history = history_store
        self._registry = tool_registry
        self._bot = bot
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, chat_id: str) -> asyncio.Lock:
        if chat_id not in self._locks:
            self._locks[chat_id] = asyncio.Lock()
        return self._locks[chat_id]

    async def process(self, chat_id: str, events: list[dict]) -> None:
        """Process a batch of messages for a chat."""
        lock = self._get_lock(chat_id)
        async with lock:
            await self._process_impl(chat_id, events)

    async def _process_impl(self, chat_id: str, events: list[dict]) -> None:
        start_time = datetime.now(timezone.utc)
        indicator = TypingIndicator(self._bot, chat_id)

        try:
            await indicator.start()

            # 1. Get conversation history
            turns = await self._history.get_recent_turns(
                chat_id, self._settings.history_turns
            )

            # 2. Get fallback context
            fallback = await self._history.get_fallback(chat_id)

            # 3. Build prompt
            now_str = datetime.now(timezone.utc).isoformat()
            system_prompt = build_system_prompt(now_str)
            user_content = build_user_prompt(turns, events, fallback)

            # 4. Call Claude API with tool loop
            messages = [{"role": "user", "content": user_content}]
            response_text = await self._call_with_tools(system_prompt, messages)

            # 5. Save conversation turn
            user_text = "\n".join(e.get("text", "") for e in events)
            elapsed_ms = int(
                (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            )
            await self._history.save_turn(chat_id, user_text, response_text, elapsed_ms)
            await self._history.clear_fallback(chat_id)

            # 6. Send response
            await indicator.stop()
            await send_response(self._bot, chat_id, response_text)

        except Exception:
            await indicator.stop()
            logger.exception("Processing failed for chat %s", chat_id)
            # Save partial context as fallback
            try:
                await self._history.save_fallback(
                    chat_id, f"Processing failed for messages: {[e.get('text', '') for e in events]}"
                )
            except Exception:
                logger.exception("Failed to save fallback context")
            raise

    async def _call_with_tools(self, system_prompt: str, messages: list[dict]) -> str:
        """Call Claude API and execute tool use loop."""
        tools = self._registry.get_tool_definitions()

        for round_num in range(MAX_TOOL_ROUNDS):
            response = await self._api_call(system_prompt, messages, tools)

            # Extract text and tool_use blocks
            text_parts = []
            tool_uses = []
            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_uses.append(block)

            if not tool_uses or response.stop_reason == "end_turn":
                # No more tool calls, return text
                return "\n".join(text_parts) if text_parts else "(no response)"

            # Execute tools and continue
            # Add assistant message with all content
            messages.append({"role": "assistant", "content": response.content})

            # Build tool results
            tool_results = []
            for tool_use in tool_uses:
                result = await self._registry.dispatch(tool_use.name, tool_use.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": result,
                    }
                )

            messages.append({"role": "user", "content": tool_results})

        return "\n".join(text_parts) if text_parts else "(max tool rounds reached)"

    async def _api_call(self, system_prompt, messages, tools):
        """Make a single API call with retry logic."""
        for attempt, delay in enumerate(RETRY_DELAYS):
            try:
                return await self._client.messages.create(
                    model=self._settings.model,
                    max_tokens=self._settings.max_tokens,
                    temperature=self._settings.temperature,
                    system=system_prompt,
                    messages=messages,
                    tools=tools,
                )
            except anthropic.RateLimitError:
                if attempt < len(RETRY_DELAYS) - 1:
                    logger.warning("Rate limited, retrying in %ds", delay)
                    await asyncio.sleep(delay)
                else:
                    raise
            except anthropic.InternalServerError:
                if attempt == 0:
                    logger.warning("Server error, retrying in 2s")
                    await asyncio.sleep(2)
                else:
                    raise
            except anthropic.APIStatusError as e:
                if e.status_code == 529:
                    logger.warning("Overloaded, retrying in %ds", OVERLOADED_DELAY)
                    await asyncio.sleep(OVERLOADED_DELAY)
                else:
                    raise

        # Final attempt without retry
        return await self._client.messages.create(
            model=self._settings.model,
            max_tokens=self._settings.max_tokens,
            temperature=self._settings.temperature,
            system=system_prompt,
            messages=messages,
            tools=tools,
        )

    async def close(self) -> None:
        await self._client.close()
