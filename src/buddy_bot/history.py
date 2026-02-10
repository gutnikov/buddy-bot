"""SQLite conversation history store."""

import asyncio
import sqlite3
from dataclasses import dataclass


@dataclass
class Turn:
    user_text: str
    bot_response: str
    created_at: str


class HistoryStore:
    def __init__(self, db_path: str, max_chars: int = 500) -> None:
        self._db_path = db_path
        self._max_chars = max_chars
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS turns (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id     TEXT NOT NULL,
                user_text   TEXT NOT NULL,
                bot_response TEXT NOT NULL,
                duration_ms INTEGER,
                created_at  TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_turns_chat_id ON turns(chat_id);
            CREATE INDEX IF NOT EXISTS idx_turns_created_at ON turns(created_at);

            CREATE TABLE IF NOT EXISTS fallback_context (
                chat_id     TEXT PRIMARY KEY,
                stdout      TEXT NOT NULL,
                updated_at  TEXT DEFAULT (datetime('now'))
            );
            """
        )
        self._conn.commit()

    def _save_turn_sync(
        self, chat_id: str, user_text: str, bot_response: str, duration_ms: int | None
    ) -> None:
        self._conn.execute(
            "INSERT INTO turns (chat_id, user_text, bot_response, duration_ms) VALUES (?, ?, ?, ?)",
            (chat_id, user_text, bot_response, duration_ms),
        )
        self._conn.commit()

    def _get_recent_turns_sync(self, chat_id: str, limit: int) -> list[Turn]:
        rows = self._conn.execute(
            """
            SELECT user_text, bot_response, created_at
            FROM turns
            WHERE chat_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (chat_id, limit),
        ).fetchall()
        turns = [
            Turn(
                user_text=row["user_text"][: self._max_chars],
                bot_response=row["bot_response"][: self._max_chars],
                created_at=row["created_at"],
            )
            for row in reversed(rows)
        ]
        return turns

    def _save_fallback_sync(self, chat_id: str, stdout: str) -> None:
        self._conn.execute(
            """
            INSERT INTO fallback_context (chat_id, stdout)
            VALUES (?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET stdout = excluded.stdout, updated_at = datetime('now')
            """,
            (chat_id, stdout),
        )
        self._conn.commit()

    def _get_fallback_sync(self, chat_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT stdout FROM fallback_context WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        if row is None:
            return None
        self._conn.execute(
            "DELETE FROM fallback_context WHERE chat_id = ?", (chat_id,)
        )
        self._conn.commit()
        return row["stdout"]

    def _clear_fallback_sync(self, chat_id: str) -> None:
        self._conn.execute(
            "DELETE FROM fallback_context WHERE chat_id = ?", (chat_id,)
        )
        self._conn.commit()

    async def save_turn(
        self,
        chat_id: str,
        user_text: str,
        bot_response: str,
        duration_ms: int | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._save_turn_sync, chat_id, user_text, bot_response, duration_ms
        )

    async def get_recent_turns(self, chat_id: str, limit: int = 20) -> list[Turn]:
        return await asyncio.to_thread(self._get_recent_turns_sync, chat_id, limit)

    async def save_fallback(self, chat_id: str, stdout: str) -> None:
        await asyncio.to_thread(self._save_fallback_sync, chat_id, stdout)

    async def get_fallback(self, chat_id: str) -> str | None:
        return await asyncio.to_thread(self._get_fallback_sync, chat_id)

    async def clear_fallback(self, chat_id: str) -> None:
        await asyncio.to_thread(self._clear_fallback_sync, chat_id)

    def close(self) -> None:
        self._conn.close()
