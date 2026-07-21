from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reg_harness.config import Settings
from reg_harness.loop import RegulationHarness
from reg_harness.types import AgentState, ToolResult
from reg_harness.tools.registry import ToolRegistry
from reg_harness.tools.base import Tool


class FakeChat:
    def __init__(self, decisions: list[dict[str, Any]]):
        self.decisions = list(decisions)

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        if not self.decisions:
            return {
                "thought": "stop",
                "action": "finalize",
                "args": {"answerable": False, "reason": "no more decisions"},
            }
        return self.decisions.pop(0)


class FakeSearch(Tool):
    name = "vector_search"
    description = "fake"

    def run(self, state: AgentState, args: dict[str, Any]) -> ToolResult:
        from reg_harness.types import EvidenceItem

        q = args.get("query") or ""
        state.evidence.append(
            EvidenceItem(kind="chunk", text=f"证据关于 {q} 不发出碰撞预警和紧急制动 6.11 右转 铁板")
        )
        return ToolResult(name=self.name, ok=True, content=f"added for {q}", data={"query": q})


class FakeGraph(Tool):
    name = "graph_search"
    description = "fake"

    def run(self, state: AgentState, args: dict[str, Any]) -> ToolResult:
        return FakeSearch().run(state, args)


class FakeCheck(Tool):
    name = "evidence_check"
    description = "fake"

    def run(self, state: AgentState, args: dict[str, Any]) -> ToolResult:
        from reg_harness.tools.evidence_check import EvidenceCheckTool

        return EvidenceCheckTool().run(state, args)


class FakeClause(Tool):
    name = "clause_lookup"
    description = "fake"

    def run(self, state: AgentState, args: dict[str, Any]) -> ToolResult:
        return ToolResult(name=self.name, ok=True, content=f"clause={args.get('clause')}")


class FakeTable(Tool):
    name = "table_lookup"
    description = "fake"

    def run(self, state: AgentState, args: dict[str, Any]) -> ToolResult:
        return ToolResult(name=self.name, ok=True, content=f"table={args.get('table')}")


class FakeCompose(Tool):
    name = "compose_answer"
    description = "fake"

    def run(self, state: AgentState, args: dict[str, Any]) -> ToolResult:
        state.final_answer = {
            "answerable": True,
            "answer": {"ok": True},
            "claims": [],
            "citations": [],
            "validation_flags": [],
        }
        state.done = True
        return ToolResult(name=self.name, ok=True, content="composed", data=state.final_answer)


class FakeFinalize(Tool):
    name = "finalize"
    description = "fake"

    def run(self, state: AgentState, args: dict[str, Any]) -> ToolResult:
        state.final_answer = {
            "answerable": False,
            "answer": {"reason": args.get("reason")},
            "validation_flags": [],
        }
        state.done = True
        return ToolResult(name=self.name, ok=True, content="finalized", data=state.final_answer)


class LoopBehaviorTests(unittest.TestCase):
    def test_no_bootstrap_by_default(self) -> None:
        settings = Settings(
            aeb_root=Path("."),
            lightrag_url="http://127.0.0.1:9621",
            llm_host="http://example",
            llm_api_key="",
            llm_model="dummy",
            llm_extra_body=None,
            default_max_steps=3,
            active_kb="gb39901",
            pilot_heuristics=False,
            enable_precise_lookup=False,
        )
        chat = FakeChat(
            [
                {
                    "thought": "search",
                    "action": "vector_search",
                    "args": {"query": "6.11 五类场景"},
                },
                {"thought": "check", "action": "evidence_check", "args": {}},
                {"thought": "answer", "action": "compose_answer", "args": {"force": True}},
            ]
        )
        registry = ToolRegistry(
            [
                FakeSearch(),
                FakeGraph(),
                FakeCheck(),
                FakeCompose(),
                FakeFinalize(),
            ]
        )
        harness = RegulationHarness(settings=settings, registry=registry, chat=chat)
        state = harness.run(
            "完整列出6.11规定的五类误响应场景，并说明共同合格判据。",
            bootstrap=False,
        )
        events = [item["event"] for item in state.trace]
        self.assertNotIn("bootstrap_tool", events)
        self.assertIn("awaiting_agent_plan", events)
        self.assertTrue(state.done)
        self.assertIsNotNone(state.final_answer)

    def test_requires_query_on_search(self) -> None:
        from reg_harness.tools.lightrag_retrieve import LightRAGRetrieveTool

        settings = Settings(
            aeb_root=Path("."),
            lightrag_url="http://127.0.0.1:9621",
            llm_host="",
            llm_api_key="",
            llm_model="",
            llm_extra_body=None,
            active_kb="gb39901",
        )
        tool = LightRAGRetrieveTool(settings, "vector_search", "naive", "x")
        state = AgentState(question="q")
        result = tool.run(state, {})
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "missing_query")


if __name__ == "__main__":
    unittest.main()
