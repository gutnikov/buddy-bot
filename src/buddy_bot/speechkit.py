"""Yandex SpeechKit STT (Speech-to-Text) client."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

RECOGNIZE_URL = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
REQUEST_TIMEOUT = 15.0


async def recognize(
    client: httpx.AsyncClient,
    audio_data: bytes,
    api_key: str,
    folder_id: str,
    lang: str = "ru-RU",
) -> str | None:
    """Send OGG audio to SpeechKit and return recognized text.

    Returns the recognized text, empty string if nothing was recognized,
    or None on error.
    """
    try:
        response = await client.post(
            RECOGNIZE_URL,
            params={"folderId": folder_id, "lang": lang, "model": "general:rc"},
            headers={
                "Authorization": f"Api-Key {api_key}",
                "Content-Type": "application/ogg",
            },
            content=audio_data,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("result", "")
    except Exception:
        logger.exception("speechkit_recognize_error")
        return None
