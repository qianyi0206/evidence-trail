from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reg_harness.guards import validate_final_answer
from reg_harness.types import AgentState, EvidenceItem


class GuardTests(unittest.TestCase):
    def test_empty_evidence_forces_refusal(self) -> None:
        state = AgentState(question="q")
        out = validate_final_answer(
            state,
            {"answerable": True, "answer": {"v": 1}, "claims": [], "citations": []},
        )
        self.assertFalse(out["answerable"])
        self.assertIn("forced_refusal_empty_evidence", out["validation_flags"])

    def test_ungrounded_speed_refused(self) -> None:
        state = AgentState(
            question="q",
            evidence=[
                EvidenceItem(kind="chunk", text="表中仅有 40 km/h 与 60 km/h 行，没有 80。")
            ],
        )
        out = validate_final_answer(
            state,
            {
                "answerable": True,
                "answer": {"max_relative_collision_speed": 50, "unit": "km/h"},
                "claims": [],
                "citations": [],
            },
        )
        self.assertFalse(out["answerable"])
        self.assertTrue(
            any("forced_refusal_ungrounded_numeric" in f for f in out["validation_flags"])
        )

    def test_ungrounded_number_in_claims_is_refused(self) -> None:
        state = AgentState(
            question="q",
            evidence=[EvidenceItem(kind="chunk", text="阈值为 60 km/h。")],
        )
        out = validate_final_answer(
            state,
            {
                "answerable": True,
                "answer": {"result": "符合要求"},
                "claims": ["阈值为 80 km/h"],
                "citations": ["E1"],
            },
        )
        self.assertFalse(out["answerable"])
        self.assertIn("forced_refusal_ungrounded_numeric", out["validation_flags"])

    def test_out_of_range_citation_is_refused(self) -> None:
        state = AgentState(
            question="q",
            evidence=[EvidenceItem(kind="chunk", text="阈值为 60 km/h。")],
        )
        out = validate_final_answer(
            state,
            {
                "answerable": True,
                "answer": {"threshold": "60 km/h"},
                "claims": ["阈值为 60 km/h"],
                "citations": ["E999"],
            },
        )
        self.assertFalse(out["answerable"])
        self.assertIn("forced_refusal_invalid_citations", out["validation_flags"])


if __name__ == "__main__":
    unittest.main()
