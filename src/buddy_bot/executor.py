"""Claude Code CLI executor — spawns `claude -p` subprocess and parses JSONL output."""

import asyncio
import json
import logging
from datetime import datetime, timezone

from buddy_bot.bot import send_response
from buddy_bot.config import Settings
from buddy_bot.history import HistoryStore
from buddy_bot.progress import format_tool_progress
from buddy_bot.prompt import build_prompt
from buddy_bot.typing_indicator import TypingIndicator

logger = logging.getLogger(__name__)

RESUME_NUDGE = "Continue. If you already answered, repeat your final response."


class ClaudeExecutor:
    def __init__(
        self,
        settings: Settings,
        history_store: HistoryStore,
        bot,
    ) -> None:
        self._settings = settings
        self._history = history_store
        self._bot = bot
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
            prompt = build_prompt(
                chat_id=chat_id,
                history_turns=turns,
                events=events,
                fallback_text=fallback,
                timezone=self._settings.user_timezone,
            )

            # 4. Run claude -p
            result_text, session_id = await self._run_claude(
                prompt, chat_id, indicator
            )

            # 5. Handle empty result — resume session
            if not result_text.strip() and session_id:
                logger.warning("Empty result, resuming session %s", session_id)
                result_text, _ = await self._resume_session(session_id)

            if not result_text.strip():
                result_text = "(no response)"

            # 6. Save conversation turn
            user_text = "\n".join(e.get("text", "") for e in events)
            elapsed_ms = int(
                (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            )
            await self._history.save_turn(chat_id, user_text, result_text, elapsed_ms)
            await self._history.clear_fallback(chat_id)

            # 7. Send response
            await indicator.stop()
            await send_response(self._bot, chat_id, result_text)

        except Exception:
            await indicator.stop()
            logger.exception("Processing failed for chat %s", chat_id)
            try:
                await self._history.save_fallback(
                    chat_id,
                    f"Processing failed for messages: {[e.get('text', '') for e in events]}",
                )
            except Exception:
                logger.exception("Failed to save fallback context")
            raise

    async def _run_claude(
        self,
        prompt: str,
        chat_id: str,
        indicator: TypingIndicator,
    ) -> tuple[str, str | None]:
        """Spawn claude -p and parse JSONL output.

        Returns (result_text, session_id).
        """
        cmd = self._build_command(prompt)
        logger.debug("Running: %s", " ".join(cmd[:5]) + " ...")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        result_text = ""
        session_id = None
        raw_lines: list[str] = []

        try:
            result_text, session_id = await asyncio.wait_for(
                self._read_stream(proc, chat_id, indicator, raw_lines),
                timeout=self._settings.claude_timeout,
            )
        except asyncio.TimeoutError:
            logger.error("Claude CLI timed out after %ds", self._settings.claude_timeout)
            proc.kill()
            await proc.wait()
            raise RuntimeError(f"Claude CLI timed out after {self._settings.claude_timeout}s")

        returncode = await proc.wait()
        if returncode != 0:
            stderr = ""
            if proc.stderr:
                stderr_bytes = await proc.stderr.read()
                stderr = stderr_bytes.decode("utf-8", errors="replace")
            logger.error(
                "Claude CLI exited with code %d: %s", returncode, stderr[:500]
            )
            raise RuntimeError(
                f"Claude CLI exited with code {returncode}: {stderr[:200]}"
            )

        return result_text, session_id

    async def _read_stream(
        self,
        proc: asyncio.subprocess.Process,
        chat_id: str,
        indicator: TypingIndicator,
        raw_lines: list[str],
    ) -> tuple[str, str | None]:
        """Read JSONL lines from claude subprocess stdout.

        Returns (result_text, session_id).
        """
        result_text = ""
        session_id = None

        assert proc.stdout is not None
        while True:
            line_bytes = await proc.stdout.readline()
            if not line_bytes:
                break

            line = line_bytes.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            raw_lines.append(line)

            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                logger.debug("Non-JSON line from claude: %s", line[:200])
                continue

            msg_type = msg.get("type")

            if msg_type == "system":
                session_id = msg.get("session_id")
                logger.debug("Claude session: %s", session_id)

            elif msg_type == "assistant":
                # Track tool_use blocks for progress messages
                message = msg.get("message", {})
                for block in message.get("content", []):
                    if block.get("type") == "tool_use":
                        tool_name = block.get("name", "")
                        progress_msg = format_tool_progress(tool_name)
                        if progress_msg:
                            logger.info("Tool: %s → %s", tool_name, progress_msg)

            elif msg_type == "result":
                result_text = msg.get("result", "")
                # result can also have session_id
                if not session_id:
                    session_id = msg.get("session_id")

        return result_text, session_id

    async def _resume_session(self, session_id: str) -> tuple[str, str | None]:
        """Resume a session with a nudge prompt."""
        cmd = [
            "claude",
            "-p", RESUME_NUDGE,
            "--output-format", "json",
            "--resume", session_id,
            "--model", self._settings.claude_model,
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=self._settings.claude_timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return "", None

        if proc.returncode != 0:
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            logger.error("Resume failed (code %d): %s", proc.returncode, stderr[:500])
            return "", None

        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        try:
            data = json.loads(stdout)
            return data.get("result", ""), data.get("session_id")
        except json.JSONDecodeError:
            # Plain text fallback
            return stdout, session_id

    def _build_command(self, prompt: str) -> list[str]:
        """Build the claude CLI command."""
        cmd = [
            "claude",
            "-p", prompt,
            "--output-format", "stream-json",
            "--verbose",
            "--model", self._settings.claude_model,
            "--mcp-config", self._settings.mcp_config_path,
        ]

        # Restrict to only MCP tools (no built-in file/bash tools)
        cmd.extend(["--allowedTools", "mcp__*"])

        return cmd

    async def close(self) -> None:
        """No persistent resources to close."""
        pass
