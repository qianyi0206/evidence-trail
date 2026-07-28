from __future__ import annotations

import math
import re
from typing import Any

from reg_harness.config import Settings
from reg_harness.knowledge.evidence_catalog import EvidenceCatalog
from reg_harness.llm import ChatClient
from reg_harness.tools.base import Tool
from reg_harness.tools.compose_answer import ComposeAnswerTool
from reg_harness.tools.evidence_check import EvidenceCheckTool
from reg_harness.tools.finalize import FinalizeTool
from reg_harness.tools.lightrag_retrieve import build_retrieve_tools
from reg_harness.tools.precise_lookup import ClauseLookupTool, TableLookupTool
from reg_harness.types import AgentState, ToolResult


# Superset of names that may exist; runtime allow-list is the registered tool set.
KNOWN_ACTIONS = frozenset(
    {
        "vector_search",
        "graph_search",
        "clause_lookup",
        "table_lookup",
        "evidence_check",
        "compose_answer",
        "finalize",
    }
)

# Backward-compatible alias used by older tests/imports.
ALLOWED_ACTIONS = KNOWN_ACTIONS


def _schema_errors(value: Any, schema: dict[str, Any], path: str = "args") -> list[str]:
    """Validate the small JSON-Schema subset used by harness tools."""
    expected = schema.get("type")
    valid_type = True
    if expected == "object":
        valid_type = isinstance(value, dict)
    elif expected == "array":
        valid_type = isinstance(value, list)
    elif expected == "string":
        valid_type = isinstance(value, str)
    elif expected == "boolean":
        valid_type = type(value) is bool
    elif expected == "integer":
        valid_type = isinstance(value, int) and not isinstance(value, bool)
    elif expected == "number":
        valid_type = (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
        )
    if not valid_type:
        return [f"{path}: expected {expected}"]

    errors: list[str] = []
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: not in enum {schema['enum']}")

    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0) or 0):
            errors.append(f"{path}: shorter than minLength")
        max_length = schema.get("maxLength")
        if max_length is not None and len(value) > int(max_length):
            errors.append(f"{path}: longer than maxLength")
        pattern = schema.get("pattern")
        if pattern and re.fullmatch(str(pattern), value) is None:
            errors.append(f"{path}: does not match required pattern")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and value < minimum:
            errors.append(f"{path}: below minimum {minimum}")
        if maximum is not None and value > maximum:
            errors.append(f"{path}: above maximum {maximum}")

    if isinstance(value, list):
        min_items = schema.get("minItems")
        max_items = schema.get("maxItems")
        if min_items is not None and len(value) < int(min_items):
            errors.append(f"{path}: fewer than minItems")
        if max_items is not None and len(value) > int(max_items):
            errors.append(f"{path}: more than maxItems")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(_schema_errors(item, item_schema, f"{path}[{index}]"))

    if isinstance(value, dict):
        properties = schema.get("properties")
        properties = properties if isinstance(properties, dict) else {}
        for required in schema.get("required") or []:
            if required not in value:
                errors.append(f"{path}.{required}: required")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{path}.{key}: unknown property")
        for key, child in value.items():
            child_schema = properties.get(key)
            if isinstance(child_schema, dict):
                errors.extend(_schema_errors(child, child_schema, f"{path}.{key}"))
    return errors


class ToolRegistry:
    def __init__(
        self,
        tools: list[Tool],
        catalog: EvidenceCatalog | None = None,
        owned_resources: list[Any] | None = None,
    ):
        self._tools = {tool.name: tool for tool in tools}
        self.catalog = catalog
        self._owned_resources = list(owned_resources or [])

    def names(self) -> list[str]:
        return sorted(self._tools)

    def allowed_actions(self) -> frozenset[str]:
        return frozenset(self._tools)

    def close(self) -> None:
        first_error: Exception | None = None
        owned_resources, self._owned_resources = self._owned_resources, []
        for resource in [*self._tools.values(), *owned_resources]:
            close = getattr(resource, "close", None)
            if not callable(close):
                continue
            try:
                close()
            except Exception as error:  # noqa: BLE001 - finish all cleanup first
                if first_error is None:
                    first_error = error
        if first_error is not None:
            raise first_error

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values()]

    def prompt_catalog(self) -> str:
        lines = ["可用工具："]
        for tool in sorted(self._tools.values(), key=lambda item: item.name):
            lines.append(f"- {tool.name}: {tool.description}")
            props = (tool.parameters or {}).get("properties") or {}
            if props:
                keys = ", ".join(props.keys())
                lines.append(f"  args: {keys}")
        return "\n".join(lines)

    def run(
        self, name: str, state: AgentState, args: dict[str, Any] | None = None
    ) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                name=name,
                ok=False,
                content=f"未知或未启用工具: {name!r}。可用: {self.names()}",
                error="unknown_tool",
                continue_loop=True,
            )
        supplied_args: Any = {} if args is None else args
        schema = tool.parameters or {"type": "object", "properties": {}}
        errors = _schema_errors(supplied_args, schema)
        if errors:
            return ToolResult(
                name=name,
                ok=False,
                content=f"工具参数不合法: {'; '.join(errors[:8])}",
                data={"validation_errors": errors[:20]},
                error="invalid_tool_arguments",
                continue_loop=True,
            )
        try:
            result = tool.run(state, supplied_args)
        except Exception as error:  # noqa: BLE001 - isolate tool failures from the loop
            return ToolResult(
                name=name,
                ok=False,
                content=f"工具执行异常: {type(error).__name__}",
                data={"exception_type": type(error).__name__},
                error="tool_exception",
                continue_loop=True,
            )
        if not isinstance(result, ToolResult):
            return ToolResult(
                name=name,
                ok=False,
                content="工具返回了不受支持的结果类型。",
                data={"result_type": type(result).__name__},
                error="invalid_tool_result",
                continue_loop=True,
            )
        return result


def load_catalog(settings: Settings) -> EvidenceCatalog:
    """Load evidence catalog for optional precise tools."""
    mode = (getattr(settings, "catalog_mode", None) or "none").strip().lower()
    if mode in {"none", ""}:
        return EvidenceCatalog([], default_kb=settings.active_kb)
    if mode == "gold":
        path = settings.evidence_jsonl
        if path and path.is_file():
            return EvidenceCatalog.from_jsonl(path, default_kb=settings.active_kb)
        return EvidenceCatalog.from_aeb_root(
            settings.aeb_root, default_kb=settings.active_kb
        )
    path = settings.evidence_jsonl
    if path and path.is_file():
        return EvidenceCatalog.from_jsonl(path, default_kb=settings.active_kb)
    return EvidenceCatalog([], default_kb=settings.active_kb)


def default_registry(
    settings: Settings,
    chat: ChatClient | None = None,
    catalog: EvidenceCatalog | None = None,
) -> ToolRegistry:
    owns_client = chat is None
    client = chat if chat is not None else ChatClient(settings)
    enable_precise = bool(getattr(settings, "enable_precise_lookup", False))
    cat = catalog
    if cat is None:
        cat = load_catalog(settings) if enable_precise else EvidenceCatalog(
            [], default_kb=settings.active_kb
        )
    tools: list[Tool] = []
    tools.extend(build_retrieve_tools(settings, catalog=cat if enable_precise else None))
    if enable_precise:
        tools.append(ClauseLookupTool(cat, settings=settings))
        tools.append(TableLookupTool(cat, settings=settings))
    tools.append(EvidenceCheckTool())
    tools.append(ComposeAnswerTool(client))
    tools.append(FinalizeTool())
    return ToolRegistry(
        tools,
        catalog=cat if enable_precise else None,
        owned_resources=[client] if owns_client else None,
    )
