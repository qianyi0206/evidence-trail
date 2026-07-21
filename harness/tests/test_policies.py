from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reg_harness.policies import infer_policy, preferred_retrieve_modes


class PolicyTests(unittest.TestCase):
    def test_complex_enumeration_generic(self) -> None:
        p = infer_policy("完整列出6.11规定的五类误响应场景，并说明共同合格判据。")
        self.assertEqual(p, "complex")
        self.assertIn("hybrid", preferred_retrieve_modes(p))

    def test_table_like_may_be_simple(self) -> None:
        p = infer_policy("表2中 N1 在 40 km/h 时的允许值是多少？")
        self.assertIn(p, {"simple", "complex"})

    def test_explicit_override(self) -> None:
        self.assertEqual(infer_policy("任意问题", "simple"), "simple")

    def test_pilot_opt_in_scope_simple(self) -> None:
        p = infer_policy("GB 39901—2025 适用于哪两类汽车？", pilot_heuristics=True)
        self.assertEqual(p, "simple")


if __name__ == "__main__":
    unittest.main()
