"""Telegram bot setup, handlers, and authorization."""

import logging
from datetime import datetime, timezone

from telegram import ReactionTypeEmoji, Update
from telegram.ext import Application, MessageHandler, filters

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


def create_application(
    token: str,
    allowed_chat_ids: list[int],
    on_message,
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

    return app
