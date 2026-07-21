from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reg_harness.config import Settings
from reg_harness.librarian import StubLibrarian
from reg_harness.runtime import build_stack
from reg_harness.schema_profiles import builtin_profiles
from reg_harness.tools.registry import default_registry


AEB_ROOT = Path(__file__).resolve().parents[2]


def _settings(**overrides) -> Settings:
    base = dict(
        aeb_root=AEB_ROOT,
        lightrag_url="http://127.0.0.1:9621",
        llm_host="",
        llm_api_key="",
        llm_model="test",
        llm_extra_body=None,
        pilot_heuristics=False,
        enable_precise_lookup=False,
        catalog_mode="none",
        evidence_jsonl=None,
        active_kb="gb39901",
    )
    base.update(overrides)
    return Settings(**base)


class FrameworkTests(unittest.TestCase):
    def test_build_stack_describe_default_skill_path(self) -> None:
        stack = build_stack(_settings())
        info = stack.describe()
        self.assertIn("gb39901", info["kbs"])
        self.assertIn("vector_search", info["tools"])
        self.assertIn("graph_search", info["tools"])
        self.assertNotIn("clause_lookup", info["tools"])
        self.assertNotIn("table_lookup", info["tools"])
        self.assertEqual(info["librarian"], "StubLibrarian")
        self.assertEqual(info.get("catalog_mode"), "none")
        self.assertFalse(info.get("pilot_heuristics"))
        self.assertFalse(info.get("enable_precise_lookup"))

    def test_precise_lookup_opt_in(self) -> None:
        reg = default_registry(_settings(enable_precise_lookup=True))
        names = reg.names()
        self.assertIn("clause_lookup", names)
        self.assertIn("table_lookup", names)

    def test_librarian_propose_only(self) -> None:
        lib = StubLibrarian(profiles=builtin_profiles())
        plan = lib.propose_ingest("corpus/foo.pdf", preferred_profile="aeb_light_duty")
        self.assertEqual(plan.schema_profile_id, "aeb_light_duty")
        self.assertEqual(plan.mode, "new_workspace")
        result = lib.run_ingest(plan)
        self.assertEqual(result["status"], "not_implemented")

    def test_tool_schemas_core_present(self) -> None:
        stack = build_stack(_settings())
        schemas = {item["name"]: item for item in stack.registry.schemas()}
        self.assertIn("vector_search", schemas)
        self.assertIn("compose_answer", schemas)
        self.assertNotIn("clause_lookup", schemas)


if __name__ == "__main__":
    unittest.main()
