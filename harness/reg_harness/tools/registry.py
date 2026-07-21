from __future__ import annotations

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


class ToolRegistry:
    def __init__(self, tools: list[Tool], catalog: EvidenceCatalog | None = None):
        self._tools = {tool.name: tool for tool in tools}
        self.catalog = catalog

    def names(self) -> list[str]:
        return sorted(self._tools)

    def allowed_actions(self) -> frozenset[str]:
        return frozenset(self._tools)

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

    def run(self, name: str, state: AgentState, args: dict[str, Any] | None = None) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                name=name,
                ok=False,
                content=f"未知或未启用工具: {name!r}。可用: {self.names()}",
                error="unknown_tool",
                continue_loop=True,
            )
        return tool.run(state, args or {})


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
    client = chat or ChatClient(settings)
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
    return ToolRegistry(tools, catalog=cat if enable_precise else None)
