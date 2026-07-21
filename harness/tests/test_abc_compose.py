"""ABC: full-bag compose, compose discipline prompt, stagnation → suggest compose."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reg_harness.config import Settings
from reg_harness.loop import RegulationHarness, _bag_signature, _suggest_compose_message
from reg_harness.prompts import SYSTEM_PROMPT
from reg_harness.tools.compose_answer import COMPOSE_SYSTEM
from reg_harness.tools.base import Tool
from reg_harness.tools.registry import ToolRegistry
from reg_harness.types import AgentState, EvidenceItem, ToolResult


class EvidenceTextAbcTests(unittest.TestCase):
    """A: no hard 16-item / 800-char caps; table-friendly compose caps."""

    def test_renders_all_items_by_default(self) -> None:
        state = AgentState(question="q")
        for i in range(20):
            state.evidence.append(
                EvidenceItem(kind="chunk", text=f"clause 6.11.{i % 5 + 1} scene-{i} " * 5)
            )
        text = state.evidence_text()
        # All items should appear unless total budget cuts the tail
        self.assertIn("[E1]", text)
        self.assertIn("[E20]", text)
        self.assertNotIn("limit=16", text)

    def test_compose_table_cap_higher_than_decision(self) -> None:
        table_body = (
            "表2 最大相对碰撞速度\n"
            + "\n".join(f"N1 静止 速度{i} 载荷 值{i}" for i in range(80))
        )
        state = AgentState(question="q")
        state.evidence.append(EvidenceItem(kind="chunk", text=table_body))
        decision = state.evidence_text(for_compose=False)
        compose = state.evidence_text(for_compose=True)
        # Compose should keep more table rows
        self.assertGreaterEqual(len(compose), len(decision))
        self.assertIn("表2", compose)

    def test_max_total_chars_notes_omission(self) -> None:
        state = AgentState(question="q")
        for i in range(30):
            state.evidence.append(
                EvidenceItem(kind="chunk", text=("长段落 " * 200) + f" id={i}")
            )
        text = state.evidence_text(max_total_chars=5000)
        self.assertIn("另有", text)
        self.assertIn("未展开", text)


class ComposePromptAbcTests(unittest.TestCase):
    """B: compose system requires full read, enumerate, partial OK."""

    def test_compose_system_discipline(self) -> None:
        text = COMPOSE_SYSTEM
        self.assertIn("通读全部", text)
        self.assertIn("枚举题", text)
        self.assertIn("不得以「感觉不全」拒答", text)
        self.assertIn("reason", text)
        self.assertIn("answerable", text)
        self.assertIn("主问题作答", text)

    def test_skill_wrapup_in_system_prompt(self) -> None:
        text = SYSTEM_PROMPT
        self.assertIn("收网", text)
        self.assertIn("compose_answer", text)
        self.assertIn("取证审核", text)
        self.assertIn("建议 compose", text)


class StagnationSuggestComposeTests(unittest.TestCase):
    """C: after stagnant retrieves, inject suggest_compose into observation."""

    def test_bag_signature_tracks_markers(self) -> None:
        a = [
            EvidenceItem(kind="chunk", text="见 6.11.1 和 6.11.2"),
            EvidenceItem(kind="relationship", text="related 6.11.3"),
        ]
        b = list(a) + [EvidenceItem(kind="chunk", text="新增 6.11.4 铁板")]
        sig_a = _bag_signature(a)
        sig_b = _bag_signature(b)
        self.assertEqual(sig_a[0], 2)
        self.assertIn("6.11.1", sig_a[1])
        self.assertGreater(sig_b[0], sig_a[0])
        self.assertTrue(sig_b[1] > sig_a[1] or len(sig_b[1] - sig_a[1]) > 0)

    def test_suggest_message_mentions_compose(self) -> None:
        state = AgentState(question="q")
        state.evidence.append(EvidenceItem(kind="chunk", text="x"))
        msg = _suggest_compose_message(state)
        self.assertIn("compose_answer", msg)
        self.assertIn("收网", msg)

    def test_loop_emits_suggest_compose_on_stagnation(self) -> None:
        class StickySearch(Tool):
            name = "graph_search"
            description = "always same bag growth=0"

            def run(self, state: AgentState, args: dict[str, Any]) -> ToolResult:
                # First call adds evidence; later calls add nothing new
                if not state.evidence:
                    state.evidence.append(
                        EvidenceItem(
                            kind="chunk",
                            text="6.11.1 6.11.2 6.11.3 6.11.4 6.11.5 误响应",
                        )
                    )
                    return ToolResult(name=self.name, ok=True, content="added")
                return ToolResult(name=self.name, ok=True, content="no new hits")

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
                return ToolResult(
                    name=self.name, ok=True, content="composed", data=state.final_answer
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
                return ToolResult(
                    name=self.name, ok=True, content="finalized", data=state.final_answer
                )

        class FakeChat:
            def __init__(self) -> None:
                self.n = 0

            def complete_json(self, system: str, user: str) -> dict[str, Any]:
                self.n += 1
                if self.n <= 3:
                    return {
                        "thought": "search again",
                        "action": "graph_search",
                        "args": {"query": "误响应 场景"},
                    }
                return {
                    "thought": "compose",
                    "action": "compose_answer",
                    "args": {"force": True},
                }

        settings = Settings(
            aeb_root=Path("."),
            lightrag_url="http://127.0.0.1:9621",
            llm_host="http://example",
            llm_api_key="",
            llm_model="dummy",
            llm_extra_body=None,
            default_max_steps=6,
            active_kb="gb39901",
            pilot_heuristics=False,
            enable_precise_lookup=False,
        )
        registry = ToolRegistry([StickySearch(), FakeCompose(), FakeFinalize()])
        harness = RegulationHarness(
            settings=settings, registry=registry, chat=FakeChat()
        )
        state = harness.run("五类误响应", bootstrap=False)
        events = [item["event"] for item in state.trace]
        self.assertIn("suggest_compose", events)
        # After second stagnant retrieve, observation should carry the hint
        suggest_obs = [
            item
            for item in state.trace
            if item.get("event") == "tool_result"
            and "收网提示" in str(item.get("content") or "")
        ]
        self.assertTrue(suggest_obs, "expected 收网提示 in some tool_result content")
        self.assertTrue(state.done)


if __name__ == "__main__":
    unittest.main()
