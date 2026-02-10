"""Tool definition and dispatch registry."""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ToolEntry:
    name: str
    description: str
    input_schema: dict
    handler: Callable


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolEntry] = {}

    def register(
        self,
        name: str,
        description: str,
        input_schema: dict,
        handler: Callable,
    ) -> None:
        self._tools[name] = ToolEntry(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=handler,
        )

    def get_tool_definitions(self) -> list[dict]:
        """Return tool definitions in Claude Messages API format."""
        return [
            {
                "name": entry.name,
                "description": entry.description,
                "input_schema": entry.input_schema,
            }
            for entry in self._tools.values()
        ]

    async def dispatch(self, name: str, input: dict) -> str:
        """Execute a tool by name and return the result as a string."""
        entry = self._tools.get(name)
        if entry is None:
            error_msg = f"Unknown tool: {name}"
            logger.error(error_msg)
            return json.dumps({"error": error_msg})

        try:
            result = await entry.handler(input)
            if isinstance(result, str):
                return result
            return json.dumps(result)
        except Exception as e:
            error_msg = f"Tool {name} failed: {e}"
            logger.exception(error_msg)
            return json.dumps({"error": error_msg})
