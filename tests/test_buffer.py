"""Tests for buddy_bot.buffer module."""

import asyncio

import pytest

from buddy_bot.buffer import MessageBuffer


def _event(text: str = "hello") -> dict:
    return {"text": text, "chat_id": "123", "from": "alex", "message_id": 1}


async def test_single_message():
    buf = MessageBuffer(debounce_delay=0.1)
    buf.add(_event("msg1"))
    events = await buf.wait_and_drain()
    assert len(events) == 1
    assert events[0]["text"] == "msg1"


async def test_batch_multiple_messages():
    buf = MessageBuffer(debounce_delay=0.2)
    buf.add(_event("msg1"))
    buf.add(_event("msg2"))
    buf.add(_event("msg3"))
    events = await buf.wait_and_drain()
    assert len(events) == 3
    assert [e["text"] for e in events] == ["msg1", "msg2", "msg3"]


async def test_timer_resets_on_new_message():
    buf = MessageBuffer(debounce_delay=0.3)
    buf.add(_event("msg1"))

    # Add another message after 0.15s (within debounce window)
    async def add_delayed():
        await asyncio.sleep(0.15)
        buf.add(_event("msg2"))

    task = asyncio.create_task(add_delayed())
    events = await buf.wait_and_drain()
    await task
    # Both messages should be in the batch
    assert len(events) == 2


async def test_is_empty():
    buf = MessageBuffer()
    assert buf.is_empty()
    buf.add(_event())
    assert not buf.is_empty()


async def test_append_requeues():
    buf = MessageBuffer(debounce_delay=0.1)
    buf.append([_event("retry1"), _event("retry2")])
    events = await buf.wait_and_drain()
    assert len(events) == 2
    assert events[0]["text"] == "retry1"


async def test_drain_clears_buffer():
    buf = MessageBuffer(debounce_delay=0.1)
    buf.add(_event("msg1"))
    events = await buf.wait_and_drain()
    assert len(events) == 1
    assert buf.is_empty()


async def test_concurrent_add_during_wait():
    buf = MessageBuffer(debounce_delay=0.2)

    async def add_messages():
        buf.add(_event("msg1"))
        await asyncio.sleep(0.1)
        buf.add(_event("msg2"))

    task = asyncio.create_task(add_messages())
    events = await buf.wait_and_drain()
    await task
    assert len(events) == 2
