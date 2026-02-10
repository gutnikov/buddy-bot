"""Todo list tool handlers."""

import json
import logging

from buddy_bot.todo import TodoStore
from buddy_bot.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

TODO_ADD_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Task title or description"},
        "due_date": {
            "type": "string",
            "description": "Due date in YYYY-MM-DD format (optional)",
        },
        "priority": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "Task priority",
            "default": "medium",
        },
    },
    "required": ["title"],
}

TODO_LIST_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["pending", "done"],
            "description": "Filter by status. Omit to show all.",
        },
        "days_ahead": {
            "type": "integer",
            "description": "Only show tasks due within this many days",
        },
    },
}

TODO_COMPLETE_SCHEMA = {
    "type": "object",
    "properties": {
        "todo_id": {"type": "integer", "description": "The task ID to mark as done"},
    },
    "required": ["todo_id"],
}

TODO_DELETE_SCHEMA = {
    "type": "object",
    "properties": {
        "todo_id": {"type": "integer", "description": "The task ID to delete"},
    },
    "required": ["todo_id"],
}


def register_todo_tools(
    registry: ToolRegistry, todo_store: TodoStore, chat_id_ref: dict
) -> None:
    """Register todo tools with the registry.

    Args:
        registry: The tool registry.
        todo_store: The TodoStore instance.
        chat_id_ref: A dict with key "chat_id" that is set before each
                     processing cycle so tools know which chat they serve.
    """

    def _chat_id() -> str:
        return chat_id_ref.get("chat_id", "default")

    async def handle_todo_add(input: dict) -> str:
        title = input["title"]
        due_date = input.get("due_date")
        priority = input.get("priority", "medium")
        item = await todo_store.add(_chat_id(), title, due_date, priority)
        return json.dumps({
            "status": "created",
            "todo_id": item.id,
            "title": item.title,
            "due_date": item.due_date,
            "priority": item.priority,
        })

    async def handle_todo_list(input: dict) -> str:
        status = input.get("status")
        days_ahead = input.get("days_ahead")
        items = await todo_store.list(_chat_id(), status, days_ahead)
        return json.dumps([
            {
                "todo_id": item.id,
                "title": item.title,
                "due_date": item.due_date,
                "priority": item.priority,
                "status": item.status,
                "created_at": item.created_at,
                "completed_at": item.completed_at,
            }
            for item in items
        ])

    async def handle_todo_complete(input: dict) -> str:
        todo_id = input["todo_id"]
        item = await todo_store.complete(_chat_id(), todo_id)
        if item is None:
            return json.dumps({"error": f"Todo #{todo_id} not found"})
        return json.dumps({
            "status": "completed",
            "todo_id": item.id,
            "title": item.title,
        })

    async def handle_todo_delete(input: dict) -> str:
        todo_id = input["todo_id"]
        deleted = await todo_store.delete(_chat_id(), todo_id)
        if not deleted:
            return json.dumps({"error": f"Todo #{todo_id} not found"})
        return json.dumps({"status": "deleted", "todo_id": todo_id})

    registry.register(
        "todo_add",
        "Add a new task to the user's todo list. Use for reminders, tasks, and planning.",
        TODO_ADD_SCHEMA,
        handle_todo_add,
    )
    registry.register(
        "todo_list",
        "List tasks from the user's todo list. Can filter by status (pending/done) and due date.",
        TODO_LIST_SCHEMA,
        handle_todo_list,
    )
    registry.register(
        "todo_complete",
        "Mark a task as completed on the user's todo list.",
        TODO_COMPLETE_SCHEMA,
        handle_todo_complete,
    )
    registry.register(
        "todo_delete",
        "Delete a task from the user's todo list.",
        TODO_DELETE_SCHEMA,
        handle_todo_delete,
    )
