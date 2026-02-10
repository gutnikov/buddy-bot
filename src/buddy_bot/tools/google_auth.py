"""Google OAuth2 credential management with SQLite token storage."""

import asyncio
import json
import logging
import sqlite3

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

logger = logging.getLogger(__name__)

CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


class GoogleAuth:
    """Manages Google OAuth2 tokens with SQLite-backed persistence."""

    def __init__(self, credentials_path: str, db_path: str) -> None:
        self._credentials_path = credentials_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_table()

    def _init_table(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS oauth_tokens (
                service     TEXT PRIMARY KEY,
                token_json  TEXT NOT NULL,
                updated_at  TEXT DEFAULT (datetime('now'))
            )
            """
        )
        self._conn.commit()

    def _load_token(self, service: str) -> Credentials | None:
        row = self._conn.execute(
            "SELECT token_json FROM oauth_tokens WHERE service = ?",
            (service,),
        ).fetchone()
        if row is None:
            return None
        return Credentials.from_authorized_user_info(json.loads(row["token_json"]))

    def _save_token(self, service: str, creds: Credentials) -> None:
        token_json = creds.to_json()
        self._conn.execute(
            """
            INSERT INTO oauth_tokens (service, token_json)
            VALUES (?, ?)
            ON CONFLICT(service) DO UPDATE SET token_json = excluded.token_json, updated_at = datetime('now')
            """,
            (service, token_json),
        )
        self._conn.commit()

    def _get_credentials_sync(self, service: str, scopes: list[str]) -> Credentials:
        creds = self._load_token(service)

        if creds and creds.valid:
            return creds

        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired token for %s", service)
            creds.refresh(Request())
            self._save_token(service, creds)
            return creds

        # No valid token — run OAuth flow
        logger.info("Starting OAuth flow for %s", service)
        flow = InstalledAppFlow.from_client_secrets_file(
            self._credentials_path, scopes
        )
        creds = flow.run_local_server(port=0)
        self._save_token(service, creds)
        return creds

    async def get_credentials(self, service: str, scopes: list[str]) -> Credentials:
        return await asyncio.to_thread(self._get_credentials_sync, service, scopes)

    def close(self) -> None:
        self._conn.close()
