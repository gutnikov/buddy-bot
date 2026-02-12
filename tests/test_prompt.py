"""Tests for buddy_bot.prompt module."""

from buddy_bot.history import Turn
from buddy_bot.prompt import build_prompt


def test_prompt_contains_system_context():
    prompt = build_prompt(
        chat_id="123",
        history_turns=[],
        events=[{"text": "hello", "from": "alex", "timestamp": "t"}],
    )
    assert "personal assistant" in prompt
    assert "Telegram" in prompt


def test_prompt_contains_chat_id():
    prompt = build_prompt(
        chat_id="42",
        history_turns=[],
        events=[{"text": "hello", "from": "alex", "timestamp": "t"}],
    )
    assert "chat_id is: 42" in prompt


def test_prompt_contains_datetime():
    prompt = build_prompt(
        chat_id="123",
        history_turns=[],
        events=[{"text": "hello", "from": "alex", "timestamp": "t"}],
        timezone="UTC",
    )
    assert "current date and time is:" in prompt


def test_prompt_no_history_no_fallback():
    events = [{"text": "hello", "from": "alex", "timestamp": "2026-02-10T14:30:00Z"}]
    prompt = build_prompt(chat_id="123", history_turns=[], events=events)
    assert "Recent conversation:" not in prompt
    assert "Before responding" in prompt  # retrieval instructions
    assert "hello" in prompt  # current messages
    assert "Previous interaction context" not in prompt


def test_prompt_with_history():
    turns = [
        Turn("what time is it?", "It's 2pm.", "2026-02-10T14:00:00"),
        Turn("thanks", "You're welcome!", "2026-02-10T14:01:00"),
    ]
    events = [{"text": "hello", "from": "alex", "timestamp": "2026-02-10T14:30:00Z"}]
    prompt = build_prompt(chat_id="123", history_turns=turns, events=events)
    assert "Recent conversation:" in prompt
    assert "User: what time is it?" in prompt
    assert "Assistant: It's 2pm." in prompt
    assert "User: thanks" in prompt
    assert "Before responding" in prompt
    assert "hello" in prompt


def test_prompt_with_fallback():
    events = [{"text": "hello", "from": "alex", "timestamp": "2026-02-10T14:30:00Z"}]
    prompt = build_prompt(
        chat_id="123",
        history_turns=[],
        events=events,
        fallback_text="partial response",
    )
    assert "Previous interaction context" in prompt
    assert "partial response" in prompt


def test_prompt_all_sections():
    turns = [Turn("msg", "resp", "2026-02-10T14:00:00")]
    events = [{"text": "new msg", "from": "alex", "timestamp": "2026-02-10T14:30:00Z"}]
    prompt = build_prompt(
        chat_id="123",
        history_turns=turns,
        events=events,
        fallback_text="fallback",
    )
    assert "Recent conversation:" in prompt
    assert "Before responding" in prompt
    assert "new msg" in prompt
    assert "Previous interaction context" in prompt


def test_history_formatting():
    turns = [
        Turn("first", "reply1", "t1"),
        Turn("second", "reply2", "t2"),
    ]
    events = [{"text": "x", "from": "a", "timestamp": "t"}]
    prompt = build_prompt(chat_id="123", history_turns=turns, events=events)
    idx1 = prompt.index("User: first")
    idx2 = prompt.index("Assistant: reply1")
    idx3 = prompt.index("User: second")
    idx4 = prompt.index("Assistant: reply2")
    assert idx1 < idx2 < idx3 < idx4


def test_event_json_formatting():
    events = [
        {"text": "msg1", "from": "alex", "timestamp": "t1"},
        {"text": "msg2", "from": "alex", "timestamp": "t2"},
    ]
    prompt = build_prompt(chat_id="123", history_turns=[], events=events)
    assert '"text": "msg1"' in prompt
    assert '"text": "msg2"' in prompt


def test_retrieval_instructions_always_present():
    prompt = build_prompt(
        chat_id="123",
        history_turns=[],
        events=[{"text": "x", "from": "a", "timestamp": "t"}],
    )
    assert "get_episodes" in prompt
    assert "search_memory_facts" in prompt
    assert "add_memory" in prompt


def test_stdout_rules():
    """Prompt should instruct Claude that stdout goes to Telegram."""
    prompt = build_prompt(
        chat_id="123",
        history_turns=[],
        events=[{"text": "x", "from": "a", "timestamp": "t"}],
    )
    assert "stdout" in prompt.lower()
    assert "Telegram" in prompt
