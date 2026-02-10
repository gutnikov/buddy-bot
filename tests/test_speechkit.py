"""Tests for buddy_bot.speechkit module."""

from unittest.mock import AsyncMock, MagicMock

import httpx

from buddy_bot.speechkit import recognize


async def test_successful_recognition():
    """SpeechKit returns recognized text."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"result": "привет мир"}

    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = mock_response

    result = await recognize(client, b"fake-audio", api_key="key", folder_id="folder")
    assert result == "привет мир"

    client.post.assert_called_once()
    call_kwargs = client.post.call_args
    assert "stt.api.cloud.yandex.net" in call_kwargs.args[0]


async def test_empty_result():
    """SpeechKit returns empty result (silence/noise)."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"result": ""}

    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = mock_response

    result = await recognize(client, b"fake-audio", api_key="key", folder_id="folder")
    assert result == ""


async def test_missing_result_key():
    """SpeechKit returns response without result key."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {}

    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = mock_response

    result = await recognize(client, b"fake-audio", api_key="key", folder_id="folder")
    assert result == ""


async def test_http_error():
    """SpeechKit returns HTTP error."""
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "401 Unauthorized",
        request=MagicMock(),
        response=MagicMock(status_code=401),
    )

    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = mock_response

    result = await recognize(client, b"fake-audio", api_key="key", folder_id="folder")
    assert result is None


async def test_network_error():
    """Network error during SpeechKit request."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.side_effect = httpx.ConnectError("Connection refused")

    result = await recognize(client, b"fake-audio", api_key="key", folder_id="folder")
    assert result is None


async def test_timeout_error():
    """Timeout during SpeechKit request."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.side_effect = httpx.ReadTimeout("Read timed out")

    result = await recognize(client, b"fake-audio", api_key="key", folder_id="folder")
    assert result is None
