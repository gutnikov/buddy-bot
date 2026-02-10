"""Tests for buddy_bot.tools.google_auth module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from buddy_bot.tools.google_auth import (
    CALENDAR_SCOPES,
    GMAIL_SCOPES,
    GoogleAuth,
)


@pytest.fixture
def auth(tmp_path):
    db_path = str(tmp_path / "tokens.db")
    return GoogleAuth(credentials_path="fake_creds.json", db_path=db_path)


def _make_valid_creds():
    creds = MagicMock()
    creds.valid = True
    creds.expired = False
    creds.refresh_token = "refresh_tok"
    creds.to_json.return_value = json.dumps({
        "token": "access_tok",
        "refresh_token": "refresh_tok",
        "client_id": "cid",
        "client_secret": "csecret",
    })
    return creds


def _make_expired_creds():
    creds = MagicMock()
    creds.valid = False
    creds.expired = True
    creds.refresh_token = "refresh_tok"
    creds.to_json.return_value = json.dumps({
        "token": "new_access_tok",
        "refresh_token": "refresh_tok",
        "client_id": "cid",
        "client_secret": "csecret",
    })
    return creds


def test_token_saving_and_loading(auth):
    """Tokens can be saved to and loaded from SQLite."""
    creds = _make_valid_creds()
    auth._save_token("google_calendar", creds)

    with patch("buddy_bot.tools.google_auth.Credentials.from_authorized_user_info") as mock_from:
        mock_from.return_value = creds
        loaded = auth._load_token("google_calendar")

    assert loaded is not None
    mock_from.assert_called_once()


def test_token_loading_missing(auth):
    """Loading a non-existent token returns None."""
    result = auth._load_token("nonexistent_service")
    assert result is None


def test_valid_token_returned_directly(auth):
    """Valid tokens are returned without refresh."""
    creds = _make_valid_creds()

    with patch.object(auth, "_load_token", return_value=creds):
        result = auth._get_credentials_sync("google_calendar", CALENDAR_SCOPES)

    assert result is creds
    creds.refresh.assert_not_called()


def test_expired_token_triggers_refresh(auth):
    """Expired tokens with refresh_token are refreshed."""
    creds = _make_expired_creds()

    with patch.object(auth, "_load_token", return_value=creds):
        with patch.object(auth, "_save_token") as mock_save:
            result = auth._get_credentials_sync("gmail", GMAIL_SCOPES)

    creds.refresh.assert_called_once()
    mock_save.assert_called_once_with("gmail", creds)
    assert result is creds


def test_missing_token_triggers_oauth_flow(auth):
    """Missing token triggers the InstalledAppFlow."""
    new_creds = _make_valid_creds()

    with patch.object(auth, "_load_token", return_value=None):
        with patch("buddy_bot.tools.google_auth.InstalledAppFlow") as MockFlow:
            mock_flow_instance = MagicMock()
            mock_flow_instance.run_local_server.return_value = new_creds
            MockFlow.from_client_secrets_file.return_value = mock_flow_instance

            with patch.object(auth, "_save_token") as mock_save:
                result = auth._get_credentials_sync("google_calendar", CALENDAR_SCOPES)

    MockFlow.from_client_secrets_file.assert_called_once_with(
        "fake_creds.json", CALENDAR_SCOPES
    )
    mock_flow_instance.run_local_server.assert_called_once_with(port=0)
    mock_save.assert_called_once_with("google_calendar", new_creds)
    assert result is new_creds


async def test_async_get_credentials(auth):
    """Async wrapper calls sync implementation."""
    creds = _make_valid_creds()

    with patch.object(auth, "_get_credentials_sync", return_value=creds) as mock_sync:
        result = await auth.get_credentials("gmail", GMAIL_SCOPES)

    mock_sync.assert_called_once_with("gmail", GMAIL_SCOPES)
    assert result is creds


def test_scopes_are_correct():
    """Verify scope constants match spec."""
    assert CALENDAR_SCOPES == ["https://www.googleapis.com/auth/calendar"]
    assert GMAIL_SCOPES == ["https://www.googleapis.com/auth/gmail.modify"]
