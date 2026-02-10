"""SQLite-backed todo/task store for day-to-day planning."""

import asyncio
import sqlite3
from dataclasses import dataclass


@dataclass
class TodoItem:
    id: int
    title: str
    due_date: str | None
    priority: str
    status: str
    created_at: str
    completed_at: str | None


class TodoStore:
    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_table()

    def _init_table(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS todos (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id       TEXT NOT NULL,
                title         TEXT NOT NULL,
                due_date      TEXT,
                priority      TEXT DEFAULT 'medium',
                status        TEXT DEFAULT 'pending',
                created_at    TEXT DEFAULT (datetime('now')),
                completed_at  TEXT
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_todos_chat_id ON todos(chat_id)"
        )
        self._conn.commit()

    def _add_sync(
        self, chat_id: str, title: str, due_date: str | None, priority: str
    ) -> TodoItem:
        cur = self._conn.execute(
            "INSERT INTO todos (chat_id, title, due_date, priority) VALUES (?, ?, ?, ?)",
            (chat_id, title, due_date, priority),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM todos WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return self._row_to_item(row)

    def _list_sync(
        self,
        chat_id: str,
        status: str | None = None,
        days_ahead: int | None = None,
    ) -> list[TodoItem]:
        query = "SELECT * FROM todos WHERE chat_id = ?"
        params: list = [chat_id]

        if status:
            query += " AND status = ?"
            params.append(status)

        if days_ahead is not None:
            query += " AND due_date IS NOT NULL AND due_date <= date('now', ? || ' days')"
            params.append(str(days_ahead))

        query += " ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 END, due_date ASC NULLS LAST, id ASC"

        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_item(r) for r in rows]

    def _complete_sync(self, chat_id: str, todo_id: int) -> TodoItem | None:
        self._conn.execute(
            "UPDATE todos SET status = 'done', completed_at = datetime('now') WHERE id = ? AND chat_id = ?",
            (todo_id, chat_id),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM todos WHERE id = ? AND chat_id = ?", (todo_id, chat_id)
        ).fetchone()
        return self._row_to_item(row) if row else None

    def _delete_sync(self, chat_id: str, todo_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM todos WHERE id = ? AND chat_id = ?", (todo_id, chat_id)
        )
        self._conn.commit()
        return cur.rowcount > 0

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> TodoItem:
        return TodoItem(
            id=row["id"],
            title=row["title"],
            due_date=row["due_date"],
            priority=row["priority"],
            status=row["status"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )

    async def add(
        self, chat_id: str, title: str, due_date: str | None = None, priority: str = "medium"
    ) -> TodoItem:
        return await asyncio.to_thread(self._add_sync, chat_id, title, due_date, priority)

    async def list(
        self, chat_id: str, status: str | None = None, days_ahead: int | None = None
    ) -> list[TodoItem]:
        return await asyncio.to_thread(self._list_sync, chat_id, status, days_ahead)

    async def complete(self, chat_id: str, todo_id: int) -> TodoItem | None:
        return await asyncio.to_thread(self._complete_sync, chat_id, todo_id)

    async def delete(self, chat_id: str, todo_id: int) -> bool:
        return await asyncio.to_thread(self._delete_sync, chat_id, todo_id)

    def close(self) -> None:
        self._conn.close()
