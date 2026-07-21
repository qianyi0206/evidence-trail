"""Bag gap detection: unresolved table refs, clause holes, format hints."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reg_harness.bag_gaps import (
    analyze_bag_gaps,
    format_gap_hints,
    table_body_present,
    unresolved_table_refs,
)
from reg_harness.prompts import SYSTEM_PROMPT
from reg_harness.tools.compose_answer import COMPOSE_SYSTEM
from reg_harness.types import AgentState, EvidenceItem


class BagGapTests(unittest.TestCase):
    def test_unresolved_table_when_only_pointer(self) -> None:
        items = [
            EvidenceItem(
                kind="chunk",
                text="儿童行人目标横穿试验开始时，试验车辆应按照表18的速度行驶，TTC不小于4 s。",
            )
        ]
        unresolved = unresolved_table_refs(items)
        self.assertIn("18", unresolved)

    def test_resolved_when_table_body_present(self) -> None:
        body = (
            "表18 儿童行人目标速度\n"
            "目标速度 5 km/h 公差 ±0.2\n"
            "试验车 20 30 40 60\n"
            "最大相对碰撞速度 0 10 20 35"
        )
        items = [
            EvidenceItem(kind="chunk", text="试验按照表18进行。"),
            EvidenceItem(kind="chunk", text=body),
        ]
        self.assertTrue(table_body_present(body, "18"))
        self.assertEqual(unresolved_table_refs(items), [])

    def test_missing_question_clause(self) -> None:
        items = [EvidenceItem(kind="chunk", text="8.2 功能安全视同条件：系统型号与软件版本规则。")]
        gaps = analyze_bag_gaps(items, "一般性能试验与功能安全分别依据8.1还是8.2？")
        self.assertIn("8.1", gaps["missing_question_clauses"])
        self.assertTrue(gaps["has_gaps"])
        hint = format_gap_hints(items, "一般性能试验与功能安全分别依据8.1还是8.2？")
        self.assertIn("取证缺口", hint)
        self.assertIn("8.1", hint)

    def test_lighting_gap_from_question(self) -> None:
        items = [EvidenceItem(kind="chunk", text="6.5 静止车辆目标试验程序描述，无照度数值。")]
        gaps = analyze_bag_gaps(items, "6.5至6.7与其他试验的最低光照强度分别是多少？")
        self.assertTrue(any("光照" in q or "lx" in q for q in gaps["suggested_queries"]))

    def test_compose_system_has_new_discipline(self) -> None:
        text = COMPOSE_SYSTEM
        self.assertIn("带单位数字", text)
        self.assertIn("证伪", text)
        self.assertIn("answerable=false", text)
        self.assertIn("见表N", text)
        # Must not bake pilot answers into the system prompt.
        for forbidden in ("0.8 s", "铁板", "表18", "1000 lx", "80 km/h"):
            self.assertNotIn(forbidden, text)

    def test_skill_mentions_table_followup(self) -> None:
        text = SYSTEM_PROMPT
        self.assertIn("表号二次检索", text)
        self.assertIn("证伪题", text)

    def test_compose_caps_raised(self) -> None:
        state = AgentState(question="q")
        # long table-like chunk (~ padded to force old 6k cap would truncate)
        row = "N1 静止 速度40 最大设计总质量 相对碰撞速度10 km/h "
        state.evidence.append(
            EvidenceItem(
                kind="chunk",
                text="表2 最大相对碰撞速度要求\n" + (row * 400),
            )
        )
        decision = state.evidence_text(for_compose=False)
        compose = state.evidence_text(for_compose=True)
        self.assertIn("表2", compose)
        self.assertGreaterEqual(len(compose), len(decision))
        # compose table cap is 9000; body should retain well past 6k raw
        self.assertGreater(len(compose), 6000)


if __name__ == "__main__":
    unittest.main()
