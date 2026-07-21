from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reg_harness.prompts import SYSTEM_PROMPT, build_user_turn


class PromptProtocolTests(unittest.TestCase):
    """Default skill prompt: coarse domain, no fine map, no precise tools, no pilot scripts."""

    def test_system_prompt_skill_core(self) -> None:
        text = SYSTEM_PROMPT
        self.assertIn("取证", text)
        self.assertIn("证据", text)
        self.assertIn("vector_search", text)
        self.assertIn("graph_search", text)
        self.assertIn("mix", text)
        self.assertIn("compose_answer", text)
        self.assertIn("finalize", text)
        self.assertIn("收网", text)
        self.assertTrue("拒答" in text or "answerable=false" in text)

    def test_system_prompt_no_precise_or_pilot_playbook(self) -> None:
        text = SYSTEM_PROMPT
        forbidden = (
            "clause_lookup",
            "table_lookup",
            "conditional_table →",
            "cross_section_synthesis",
            "tools_prefer",
            "五类误响应",
            "铁板",
            "表1–表12",
            "6.11",
            "条款树",
        )
        for token in forbidden:
            self.assertNotIn(token, text, f"should not appear in coarse skill: {token!r}")

    def test_user_turn_minimal_default(self) -> None:
        turn = build_user_turn(
            question="任意法规问题",
            evidence_preview="（证据袋为空）",
            last_observation="尚未检索",
            step=1,
            max_steps=6,
        )
        self.assertIn("任意法规问题", turn)
        self.assertIn("证据袋", turn)
        self.assertNotIn("路由摘要", turn)
        self.assertNotIn("结构信号", turn)


if __name__ == "__main__":
    unittest.main()
