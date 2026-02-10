"""Tests for buddy_bot.todo module."""

import pytest

from buddy_bot.todo import TodoStore


@pytest.fixture
def store(tmp_path):
    s = TodoStore(str(tmp_path / "test.db"))
    yield s
    s.close()


async def test_add_and_list(store):
    item = await store.add("chat1", "Buy milk", "2026-02-15", "high")
    assert item.title == "Buy milk"
    assert item.due_date == "2026-02-15"
    assert item.priority == "high"
    assert item.status == "pending"
    assert item.id is not None

    items = await store.list("chat1")
    assert len(items) == 1
    assert items[0].title == "Buy milk"


async def test_complete(store):
    item = await store.add("chat1", "Do laundry")
    result = await store.complete("chat1", item.id)
    assert result is not None
    assert result.status == "done"
    assert result.completed_at is not None


async def test_complete_nonexistent(store):
    result = await store.complete("chat1", 999)
    assert result is None


async def test_delete(store):
    item = await store.add("chat1", "Temporary task")
    deleted = await store.delete("chat1", item.id)
    assert deleted is True

    items = await store.list("chat1")
    assert len(items) == 0


async def test_delete_nonexistent(store):
    deleted = await store.delete("chat1", 999)
    assert deleted is False


async def test_filter_by_status(store):
    await store.add("chat1", "Pending task")
    item2 = await store.add("chat1", "Done task")
    await store.complete("chat1", item2.id)

    pending = await store.list("chat1", status="pending")
    assert len(pending) == 1
    assert pending[0].title == "Pending task"

    done = await store.list("chat1", status="done")
    assert len(done) == 1
    assert done[0].title == "Done task"


async def test_filter_by_days_ahead(store):
    await store.add("chat1", "Soon", "2026-02-11")
    await store.add("chat1", "Far away", "2099-12-31")
    await store.add("chat1", "No date")

    items = await store.list("chat1", days_ahead=30)
    # Only "Soon" has a due_date within 30 days (from 2026-02-10)
    assert len(items) == 1
    assert items[0].title == "Soon"


async def test_per_chat_isolation(store):
    await store.add("chat1", "Chat 1 task")
    await store.add("chat2", "Chat 2 task")

    items1 = await store.list("chat1")
    items2 = await store.list("chat2")

    assert len(items1) == 1
    assert items1[0].title == "Chat 1 task"
    assert len(items2) == 1
    assert items2[0].title == "Chat 2 task"


async def test_priority_ordering(store):
    await store.add("chat1", "Low prio", priority="low")
    await store.add("chat1", "High prio", priority="high")
    await store.add("chat1", "Medium prio", priority="medium")

    items = await store.list("chat1")
    assert [i.title for i in items] == ["High prio", "Medium prio", "Low prio"]
