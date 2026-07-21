from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reg_harness.compact import _focus_terms
from reg_harness.intent import resolve_intent
from reg_harness.slots import build_slots, pilot_answer_cues_in_keywords
from reg_harness.structure import parse_structure_signals


PILOT_Q = "完整列出6.11规定的五类误响应场景，并说明所有场景共同的合格判据。"
NEUTRAL_Q = "本标准对系统故障警告信号有何一般性要求？"


class P1ControlTests(unittest.TestCase):
    def test_structure_signals_reflect_question_only(self) -> None:
        sig = parse_structure_signals(PILOT_Q)
        self.assertIn("6.11", sig.clause_candidates)
        self.assertTrue(sig.has_enumeration_cue)
        # Scene names not in question must not be fabricated into clause list
        self.assertNotIn("铁板", sig.clause_candidates)

    def test_default_intent_no_tools_prefer_playbook(self) -> None:
        r = resolve_intent(PILOT_Q, pilot_heuristics=False)
        self.assertEqual(r.tools_prefer, [])
        r2 = resolve_intent(NEUTRAL_Q, pilot_heuristics=False)
        self.assertEqual(r2.tools_prefer, [])

    def test_default_slots_no_external_pilot_cues(self) -> None:
        for q in (PILOT_Q, NEUTRAL_Q):
            slots = build_slots(q, "complex", pilot_heuristics=False)
            self.assertEqual(pilot_answer_cues_in_keywords(slots, q), [])

    def test_compact_focus_terms_subset_of_question_or_parse(self) -> None:
        terms = _focus_terms(NEUTRAL_Q)
        for term in terms:
            # Every focus term must appear in the question or be a trivial parse form
            self.assertTrue(
                term in NEUTRAL_Q or term.casefold() in NEUTRAL_Q.casefold(),
                f"focus term {term!r} not from question",
            )

    def test_pilot_flag_on_differs(self) -> None:
        off = resolve_intent(PILOT_Q, pilot_heuristics=False)
        on = resolve_intent(PILOT_Q, pilot_heuristics=True)
        self.assertNotEqual(off.tools_prefer, on.tools_prefer)
        self.assertTrue(on.tools_prefer)


if __name__ == "__main__":
    unittest.main()
