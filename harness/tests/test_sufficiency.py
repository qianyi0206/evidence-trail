"""Sufficiency audit + force-compose anti-spin loop."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reg_harness.config import Settings
from reg_harness.loop import RegulationHarness
from reg_harness.sufficiency import audit_bag_sufficiency
from reg_harness.tools.base import Tool
from reg_harness.tools.registry import ToolRegistry
from reg_harness.types import AgentState, EvidenceItem, ToolResult


class SufficiencyAuditTests(unittest.TestCase):
    def test_empty_bag_not_sufficient(self) -> None:
        audit = audit_bag_sufficiency("6.11 五类场景？", [])
        self.assertFalse(audit.sufficient)
        self.assertTrue(audit.hard_gaps)

    def test_missing_question_clause_is_hard_gap(self) -> None:
        items = [EvidenceItem(kind="chunk", text="8.2 功能安全视同条件：系统型号。")]
        audit = audit_bag_sufficiency(
            "一般性能与功能安全分别依据8.1还是8.2？",
            items,
        )
        self.assertFalse(audit.sufficient)
        self.assertIn("8.1", audit.missing_clauses)
        self.assertTrue(audit.hard_gaps)

    def test_rich_bag_without_hard_gaps_is_sufficient(self) -> None:
        body = (
            "6.11 误响应试验包含下列场景。"
            "6.11.1 车辆跟车过程中车辆目标右转。"
            "6.11.2 相邻车道静止车辆目标。"
            "6.11.3 车道内铁板。"
            "6.11.4 车辆直行经过同向运动的成年行人目标。"
            "6.11.5 车辆直行经过对向静止的自行车目标。"
            "5.4 若不存在碰撞危险，系统不应发出碰撞预警和紧急制动。"
        ) * 2
        items = [EvidenceItem(kind="chunk", text=body)]
        audit = audit_bag_sufficiency(
            "完整列出6.11规定的五类误响应场景，并说明所有场景共同的合格判据。",
            items,
        )
        self.assertTrue(audit.sufficient)
        self.assertFalse(audit.hard_gaps)
        self.assertIn("足够", audit.observation_block())


class FakeChat:
    def __init__(self, decisions: list[dict[str, Any]]):
        self.decisions = list(decisions)
        self.calls = 0

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        self.calls += 1
        if not self.decisions:
            return {
                "thought": "fallback",
                "action": "finalize",
                "args": {"answerable": False, "reason": "no decisions left"},
            }
        return self.decisions.pop(0)


class SpinSearch(Tool):
    """First call adds evidence; later identical signatures return duplicate_call."""

    name = "vector_search"
    description = "fake spin"

    def run(self, state: AgentState, args: dict[str, Any]) -> ToolResult:
        query = str(args.get("query") or "").strip()
        mode = str(args.get("mode") or "naive")
        signature = f"{self.name}|{mode}|{query}"
        if state.register_call(signature):
            return ToolResult(
                name=self.name,
                ok=False,
                content=f"重复检索已拦截：{signature}。",
                error="duplicate_call",
                continue_loop=True,
            )
        # One rich chunk so sufficiency can pass after spin detection.
        text = (
            "6.11 五类误响应：右转、相邻车道静止、车道内铁板、同向行人、对向自行车。"
            "合格判据：不存在碰撞危险时不发出碰撞预警且不实施紧急制动。"
        ) * 3
        state.evidence.append(EvidenceItem(kind="chunk", text=text, file_path="n.md"))
        return ToolResult(
            name=self.name,
            ok=True,
            content=f"added=1 bag_size={len(state.evidence)}",
            data={"added": 1, "query": query},
            continue_loop=True,
        )


class FakeGraph(Tool):
    name = "graph_search"
    description = "fake"

    def run(self, state: AgentState, args: dict[str, Any]) -> ToolResult:
        return SpinSearch().run(state, args)


class FakeCompose(Tool):
    name = "compose_answer"
    description = "fake"

    def run(self, state: AgentState, args: dict[str, Any]) -> ToolResult:
        state.final_answer = {
            "answerable": True,
            "answer": {"ok": True},
            "claims": ["composed"],
            "citations": ["E1"],
            "validation_flags": [],
        }
        state.done = True
        return ToolResult(
            name=self.name,
            ok=True,
            content="compose_ok",
            data=state.final_answer,
            continue_loop=False,
        )


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


class FakeCheck(Tool):
    name = "evidence_check"
    description = "fake"

    def run(self, state: AgentState, args: dict[str, Any]) -> ToolResult:
        return ToolResult(
            name=self.name,
            ok=True,
            content=f"bag={len(state.evidence)}",
            continue_loop=True,
        )


class ForceComposeLoopTests(unittest.TestCase):
    def test_duplicate_streak_forces_compose(self) -> None:
        settings = Settings(
            aeb_root=Path("."),
            lightrag_url="http://127.0.0.1:9621",
            llm_host="http://example",
            llm_api_key="",
            llm_model="dummy",
            llm_extra_body=None,
            default_max_steps=10,
            active_kb="gb39901",
            pilot_heuristics=False,
            enable_precise_lookup=False,
        )
        # Model keeps requesting the same retrieve; loop must force compose.
        chat = FakeChat(
            [
                {
                    "thought": "search1",
                    "action": "vector_search",
                    "args": {"query": "6.11.3 铁板", "mode": "naive"},
                },
                {
                    "thought": "search2 same",
                    "action": "vector_search",
                    "args": {"query": "6.11.3 铁板", "mode": "naive"},
                },
                {
                    "thought": "search3 same again",
                    "action": "vector_search",
                    "args": {"query": "6.11.3 铁板", "mode": "naive"},
                },
                {
                    "thought": "would keep spinning",
                    "action": "vector_search",
                    "args": {"query": "6.11.3 铁板", "mode": "naive"},
                },
            ]
        )
        registry = ToolRegistry(
            [SpinSearch(), FakeGraph(), FakeCheck(), FakeCompose(), FakeFinalize()]
        )
        harness = RegulationHarness(settings=settings, registry=registry, chat=chat)
        state = harness.run(
            "完整列出6.11规定的五类误响应场景，并说明共同合格判据。",
            max_steps=10,
            bootstrap=False,
        )
        events = [item["event"] for item in state.trace]
        self.assertIn("sufficiency_audit", events)
        self.assertIn("force_compose", events)
        self.assertIn("forced_compose", events)
        self.assertTrue(state.done)
        self.assertTrue((state.final_answer or {}).get("answerable"))
        # Must not burn all 10 model decisions.
        self.assertLessEqual(chat.calls, 4)
        self.assertLess(state.step, 10)


if __name__ == "__main__":
    unittest.main()
