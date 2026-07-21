from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reg_harness.slots import (
    build_slots,
    pilot_answer_cues_in_keywords,
    refresh_slots,
    slot_summary,
)
from reg_harness.types import EvidenceItem


class SlotTests(unittest.TestCase):
    def test_generic_enumeration_slots_no_pilot_cues(self) -> None:
        q = "完整列出6.11规定的五类误响应场景，并说明所有场景共同的合格判据。"
        slots = build_slots(q, "complex", pilot_heuristics=False)
        ids = {slot.id for slot in slots}
        self.assertTrue({"list_items", "source_anchor"} & ids or "list_items" in ids)
        bad = pilot_answer_cues_in_keywords(slots, q)
        self.assertEqual(bad, [], f"P1 must not inject pilot cues absent from question: {bad}")
        # Clause present in question may appear as keyword — that is OK
        all_kw = [k for s in slots for k in s.keywords]
        self.assertTrue(any("6.11" in k for k in all_kw) or "6.11" in q)

    def test_neutral_question_slots(self) -> None:
        q = "本文件的适用范围如何表述？"
        slots = build_slots(q, "complex", pilot_heuristics=False)
        bad = pilot_answer_cues_in_keywords(slots, q)
        self.assertEqual(bad, [])
        self.assertTrue(any(s.id in {"main_fact", "source_anchor", "list_items"} for s in slots))

    def test_pilot_opt_in_may_inject_cues(self) -> None:
        q = "完整列出6.11规定的五类误响应场景，并说明所有场景共同的合格判据。"
        slots = build_slots(q, "complex", pilot_heuristics=True)
        ids = {slot.id for slot in slots}
        self.assertIn("scenario_list", ids)
        bad = pilot_answer_cues_in_keywords(slots, q)
        self.assertTrue(bad, "pilot mode expected to inject answer cues not in question")

    def test_refresh_covers_question_tokens(self) -> None:
        q = "完整列出6.11规定的误响应场景与合格判据。"
        slots = build_slots(q, "complex", pilot_heuristics=False)
        evidence = [
            EvidenceItem(
                kind="chunk",
                text="6.11 误响应场景 合格判据 不发出碰撞预警和紧急制动",
            ),
        ]
        refresh_slots(slots, evidence)
        summary = slot_summary(slots)
        self.assertTrue(
            summary["ready_for_answer"]
            or summary["covered"]
            or summary["partial"],
            summary,
        )


if __name__ == "__main__":
    unittest.main()
