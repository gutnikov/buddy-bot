"""Tests for buddy_bot.history module."""

import pytest

from buddy_bot.history import HistoryStore


@pytest.fixture
def store(tmp_path):
    s = HistoryStore(str(tmp_path / "test.db"))
    yield s
    s.close()


async def test_table_auto_creation(tmp_path):
    s = HistoryStore(str(tmp_path / "fresh.db"))
    # Should not raise
    turns = await s.get_recent_turns("chat1")
    assert turns == []
    s.close()


async def test_save_and_get_turns(store):
    await store.save_turn("chat1", "hello", "hi there", 100)
    turns = await store.get_recent_turns("chat1")
    assert len(turns) == 1
    assert turns[0].user_text == "hello"
    assert turns[0].bot_response == "hi there"


async def test_turn_limit(store):
    for i in range(30):
        await store.save_turn("chat1", f"msg-{i}", f"resp-{i}")
    turns = await store.get_recent_turns("chat1", limit=20)
    assert len(turns) == 20
    # Should be the latest 20, in chronological order
    assert turns[0].user_text == "msg-10"
    assert turns[-1].user_text == "msg-29"


async def test_chronological_ordering(store):
    await store.save_turn("chat1", "first", "r1")
    await store.save_turn("chat1", "second", "r2")
    await store.save_turn("chat1", "third", "r3")
    turns = await store.get_recent_turns("chat1")
    assert turns[0].user_text == "first"
    assert turns[1].user_text == "second"
    assert turns[2].user_text == "third"


async def test_per_turn_truncation(tmp_path):
    store = HistoryStore(str(tmp_path / "trunc.db"), max_chars=10)
    await store.save_turn("chat1", "a" * 100, "b" * 100)
    turns = await store.get_recent_turns("chat1")
    assert len(turns[0].user_text) == 10
    assert len(turns[0].bot_response) == 10
    store.close()


async def test_fallback_save_get_clear(store):
    # Initially no fallback
    assert await store.get_fallback("chat1") is None

    # Save fallback
    await store.save_fallback("chat1", "partial response")
    val = await store.get_fallback("chat1")
    assert val == "partial response"

    # get_fallback consumes it
    assert await store.get_fallback("chat1") is None


async def test_fallback_consumed_on_read(store):
    await store.save_fallback("chat1", "partial")
    first = await store.get_fallback("chat1")
    assert first == "partial"
    second = await store.get_fallback("chat1")
    assert second is None


async def test_fallback_upsert(store):
    await store.save_fallback("chat1", "old")
    await store.save_fallback("chat1", "new")
    val = await store.get_fallback("chat1")
    assert val == "new"


async def test_clear_fallback(store):
    await store.save_fallback("chat1", "data")
    await store.clear_fallback("chat1")
    assert await store.get_fallback("chat1") is None


async def test_per_chat_isolation(store):
    await store.save_turn("chat_a", "msg_a", "resp_a")
    await store.save_turn("chat_b", "msg_b", "resp_b")

    turns_a = await store.get_recent_turns("chat_a")
    turns_b = await store.get_recent_turns("chat_b")

    assert len(turns_a) == 1
    assert turns_a[0].user_text == "msg_a"
    assert len(turns_b) == 1
    assert turns_b[0].user_text == "msg_b"


async def test_duration_ms_optional(store):
    await store.save_turn("chat1", "msg", "resp")
    await store.save_turn("chat1", "msg2", "resp2", 500)
    turns = await store.get_recent_turns("chat1")
    assert len(turns) == 2
