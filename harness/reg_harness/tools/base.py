from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from reg_harness.types import AgentState, ToolResult


class Tool(ABC):
    name: str
    description: str
    # JSON-schema-like parameter description for prompt injection
    parameters: dict[str, Any] = {}

    @abstractmethod
    def run(self, state: AgentState, args: dict[str, Any]) -> ToolResult:
        raise NotImplementedError

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters or {"type": "object", "properties": {}},
        }
