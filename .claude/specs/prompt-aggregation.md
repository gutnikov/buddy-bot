# Prompt Aggregation and User Input Collection

## Overview
User messages in a topic are collected and aggregated into a prompt through a prompt-master. The user refines the prompt iteratively, with the ability to revert changes step by step, until they decide to send it to the tmux session.

## Goals
- Aggregate user input across multiple messages into a single prompt
- Allow iterative refinement of the prompt before sending to the session
- Provide step-by-step revert to any previous prompt version
- Allow full reset to start over

## Requirements

### Message Flow
- When a user sends a text message (or voice message) in a bound topic, the bot passes it to the prompt-master
- Voice messages are transcribed first, then the transcribed text is treated identically to typed text (no separate transcription reply — only the aggregated prompt is shown)
- The prompt-master processes the input and returns a result
- The bot displays the result message with applicable buttons (see Button Visibility)
- Only messages in bound topics are aggregated; unbound topics are ignored
- The existing `echo_in_topic` stub handler is removed and replaced by prompt aggregation

### Buttons
- **Run** — Pushes the aggregated prompt to the tmux session (not implemented in this spec; for now, just respond with a "Run" confirmation message)
- **Revert** — Sets the prompt back to the previous version (one step back)
- **Reset** — Erases the entire history and makes the current prompt empty, allowing the user to start from the beginning
- Only admins can press the buttons

### Button Visibility
- Only show buttons that have an effect in the current state
- Empty prompt: no buttons shown
- Single message (no prior version): show **Run** and **Reset** only
- Multiple messages: show all three (**Run**, **Revert**, **Reset**)

### Revert Behavior
- The user must be able to revert step by step, all the way back to the very first version
- This requires storing the full message history (all intermediate prompt versions)
- Reverting past the first message is equivalent to Reset: prompt becomes empty, history is cleared, bot message is deleted

### Prompt-Master
- Lives in a separate module (`bot/prompt_master.py`)
- Uses `claude -p` (Claude CLI in pipe mode) to process input
- The prompt-master receives the previous prompt state and the new user input, and returns the updated prompt
- Invoked as an async subprocess: `claude -p --system-prompt <system_prompt>` with the user message piped to stdin
- The user message sent to claude combines the previous state and new input (e.g., `"Previous state:\n{previous}\n\nNew input:\n{new_input}"`)
- System prompt:

```
# Specification Accumulation Assistant — System Prompt

You are an assistant-editor responsible for maintaining a single evolving **text** formatted in Markdown style.

On each turn, you receive:
- The previous state of the text (Markdown-formatted)
- New user input (free-form text)

Your task is to:
- Preserve all existing text
- Add the new input to the existing text
- Apply minimal Markdown-style structuring for clarity
- Keep the meaning exactly as provided by the user

Rules:
- Do not add ideas, assumptions, or interpretations
- Do not improve, redesign, or complete thoughts
- Do not remove or rewrite existing text unless explicitly instructed
- Do not guess or resolve ambiguities

Guidelines:
- Treat user input as the only source of truth
- Prefer addition over modification
- Use headings and bullet lists only when helpful
- Create new sections only if necessary

Output:
- Return only the updated text (Markdown-formatted)
- No explanations, comments, or meta-text
```

### Storage
- Message history stored in-memory, keyed by `(chat_id, topic_id)`
- One shared prompt per topic — all users in the topic contribute to the same prompt
- The bot's response `message_id` is stored alongside the history for in-place editing
- State is lost on restart
- State is cleared when the topic is detached (`/detach` or auto-detach)

### Display
- The prompt-master response is shown using HTML parse mode with `<pre>` tags (consistent with existing codebase patterns)
- If `edit_message_text` fails (e.g., message deleted externally), fall back to sending a new message

### Message Editing
- When the user sends new input while a prompt message already exists: edit the existing bot message in-place
- After a **Run**, the next user input creates a new message (fresh prompt cycle)
- After a **Reset**, the bot message is deleted; next input creates a new message
