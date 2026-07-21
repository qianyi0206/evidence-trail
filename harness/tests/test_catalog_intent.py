from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reg_harness.intent import resolve_intent
from reg_harness.knowledge.evidence_catalog import EvidenceCatalog


AEB_ROOT = Path(__file__).resolve().parents[2]


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = AEB_ROOT / "benchmark" / "data" / "evidence.jsonl"
        cls.catalog = EvidenceCatalog.from_jsonl(path, default_kb="gb39901")

    def test_loads_records(self) -> None:
        self.assertGreater(len(self.catalog.records), 20)

    def test_clause_lookup_6_11(self) -> None:
        hits = self.catalog.lookup_clause("6.11", kb="gb39901")
        self.assertTrue(any(item.id == "gb39901:clause:6.11" for item in hits))

    def test_table_lookup_n1_40(self) -> None:
        hits = self.catalog.lookup_table(
            2, vehicle="N1", ego_kmh=40, load_state="最大设计总质量", kb="gb39901"
        )
        ids = [item.id for item in hits]
        self.assertIn("gb39901:table:2:row:40", ids)

    def test_match_ids_from_clause_marker(self) -> None:
        text = "relation_type=VERIFIED_BY; source_clause=5.4; evidence=按照6.11进行试验。"
        ids = self.catalog.match_ids_for_text(text, kb="gb39901")
        self.assertTrue(any("5.4" in eid or "6.11" in eid for eid in ids))


class IntentTests(unittest.TestCase):
    """Default path is P1 (pilot_heuristics=False)."""

    def test_table_intent_generic(self) -> None:
        result = resolve_intent(
            "N1 类试验车辆以 40 km/h 驶向静止车辆目标时，在最大设计总质量状态下允许的最大相对碰撞速度是多少？"
        )
        self.assertEqual(result.kb, ["gb39901"])
        self.assertTrue(result.need_table or "40" in str(result.structure.get("speeds_kmh")))
        self.assertEqual(result.tools_prefer, [])
        self.assertNotEqual(result.intent, "conditional_table")  # pilot label only

    def test_synthesis_intent_generic(self) -> None:
        result = resolve_intent(
            "完整列出6.11规定的五类误响应场景，并说明所有场景共同的合格判据。"
        )
        self.assertEqual(result.kb, ["gb39901"])
        self.assertIn("6.11", result.structure.get("clause_candidates") or [])
        self.assertEqual(result.tools_prefer, [])
        self.assertTrue(result.need_graph or result.intent == "synthesis_or_compare")

    def test_kb_always_present(self) -> None:
        result = resolve_intent("随便一问")
        self.assertEqual(result.kb, ["gb39901"])

    def test_pilot_opt_in_restores_playbook(self) -> None:
        result = resolve_intent(
            "完整列出6.11规定的五类误响应场景，并说明所有场景共同的合格判据。",
            pilot_heuristics=True,
        )
        self.assertEqual(result.intent, "cross_section_synthesis")
        self.assertIn("clause_lookup", result.tools_prefer)


if __name__ == "__main__":
    unittest.main()
