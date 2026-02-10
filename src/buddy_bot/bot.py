"""Telegram bot setup, handlers, and authorization."""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone

import httpx
from telegram import ReactionTypeEmoji, Update
from telegram.ext import Application, MessageHandler, filters

from buddy_bot.config import Settings
from buddy_bot.speechkit import recognize

logger = logging.getLogger(__name__)


def is_authorized(chat_id: int, allowed_ids: list[int]) -> bool:
    return chat_id in allowed_ids


def extract_event(update: Update) -> dict | None:
    """Extract a standard event dict from a Telegram update."""
    msg = update.message
    if msg is None:
        return None

    text = msg.text or msg.caption or ""
    if not text:
        return None

    return {
        "text": text,
        "from": msg.from_user.first_name if msg.from_user else "unknown",
        "chat_id": str(msg.chat_id),
        "message_id": msg.message_id,
        "timestamp": datetime.fromtimestamp(msg.date.timestamp(), tz=timezone.utc).isoformat(),
    }


def split_message(text: str, max_length: int = 4096) -> list[str]:
    """Split a message into chunks at paragraph boundaries."""
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break

        # Try to split at paragraph boundary
        split_idx = text.rfind("\n\n", 0, max_length)
        if split_idx == -1:
            # Try single newline
            split_idx = text.rfind("\n", 0, max_length)
        if split_idx == -1:
            # Try space
            split_idx = text.rfind(" ", 0, max_length)
        if split_idx == -1:
            # Hard split
            split_idx = max_length

        chunks.append(text[:split_idx])
        text = text[split_idx:].lstrip("\n")

    return chunks


async def send_response(bot, chat_id: str, text: str) -> None:
    """Send a response, splitting if too long."""
    chunks = split_message(text)
    for chunk in chunks:
        try:
            await bot.send_message(chat_id=int(chat_id), text=chunk)
        except Exception:
            logger.exception("Failed to send message to chat %s", chat_id)


async def react_eyes(bot, chat_id: int, message_id: int) -> None:
    """React with eyes emoji to acknowledge receipt. Fire-and-forget."""
    try:
        await bot.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=[ReactionTypeEmoji("👀")],
        )
    except Exception:
        logger.debug("Failed to set reaction on message %d", message_id)


async def extract_voice_event(
    update: Update,
    bot,
    http_client: httpx.AsyncClient,
    settings: Settings,
) -> dict | None:
    """Download voice audio, transcribe via SpeechKit, return event dict.

    Returns a standard event dict with transcribed text, or None if
    transcription failed (error replies are sent directly).
    """
    msg = update.message
    if msg is None or msg.voice is None:
        return None

    if msg.from_user and msg.from_user.is_bot:
        return None

    voice = msg.voice

    if voice.duration > settings.max_voice_duration:
        await msg.reply_text(
            f"Voice message too long, max {settings.max_voice_duration} seconds."
        )
        return None

    # Download audio
    buf = io.BytesIO()
    file = await bot.get_file(voice.file_id)
    await file.download_to_memory(buf)
    audio_data = buf.getvalue()

    # Transcribe
    text = await recognize(
        http_client,
        audio_data,
        api_key=settings.speechkit_api_key,
        folder_id=settings.yandex_folder_id,
        lang=settings.speechkit_lang,
    )

    if text is None:
        await msg.reply_text("Could not transcribe voice message.")
        return None

    if not text:
        await msg.reply_text("Could not recognize speech.")
        return None

    return {
        "text": text,
        "from": msg.from_user.first_name if msg.from_user else "unknown",
        "chat_id": str(msg.chat_id),
        "message_id": msg.message_id,
        "timestamp": datetime.fromtimestamp(msg.date.timestamp(), tz=timezone.utc).isoformat(),
        "source": "voice",
        "voice_duration": voice.duration,
    }


def create_application(
    token: str,
    allowed_chat_ids: list[int],
    on_message,
    http_client: httpx.AsyncClient | None = None,
    settings: Settings | None = None,
) -> Application:
    """Create the Telegram bot Application with message handlers."""
    app = Application.builder().token(token).build()

    async def handle_message(update: Update, context) -> None:
        msg = update.message
        if msg is None:
            return

        if not is_authorized(msg.chat_id, allowed_chat_ids):
            logger.debug("Ignoring unauthorized chat_id=%d", msg.chat_id)
            return

        event = extract_event(update)
        if event is None:
            return

        # Fire-and-forget reaction
        await react_eyes(context.bot, msg.chat_id, msg.message_id)

        await on_message(event)

    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO | filters.Document.ALL, handle_message))

    # Register voice handler only when SpeechKit is configured
    if http_client and settings and settings.speechkit_api_key:

        async def handle_voice(update: Update, context) -> None:
            msg = update.message
            if msg is None:
                return

            if not is_authorized(msg.chat_id, allowed_chat_ids):
                logger.debug("Ignoring unauthorized chat_id=%d", msg.chat_id)
                return

            await react_eyes(context.bot, msg.chat_id, msg.message_id)

            event = await extract_voice_event(update, context.bot, http_client, settings)
            if event is None:
                return

            await on_message(event)

        app.add_handler(MessageHandler(filters.VOICE, handle_voice))
        logger.info("Voice message handler registered (SpeechKit enabled)")

    return app
