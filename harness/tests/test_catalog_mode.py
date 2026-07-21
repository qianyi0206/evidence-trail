from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reg_harness.config import Settings, load_settings
from reg_harness.kb import KnowledgeBaseRegistry
from reg_harness.runtime import build_stack
from reg_harness.tools.registry import default_registry, load_catalog
from reg_harness.types import AgentState


AEB_ROOT = Path(__file__).resolve().parents[2]


def _minimal_settings(**overrides) -> Settings:
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


class CatalogModeTests(unittest.TestCase):
    def test_default_load_settings(self) -> None:
        import os

        old = {
            k: os.environ.pop(k, None)
            for k in (
                "HARNESS_CATALOG_MODE",
                "HARNESS_EVIDENCE_JSONL",
                "HARNESS_ENABLE_PRECISE_LOOKUP",
                "HARNESS_PILOT_HEURISTICS",
            )
        }
        try:
            cfg = load_settings(aeb_root=AEB_ROOT)
            self.assertEqual(cfg.catalog_mode, "none")
            self.assertFalse(cfg.pilot_heuristics)
            self.assertFalse(cfg.enable_precise_lookup)
        finally:
            for k, v in old.items():
                if v is not None:
                    os.environ[k] = v

    def test_load_catalog_none_is_empty(self) -> None:
        cat = load_catalog(_minimal_settings(catalog_mode="none"))
        self.assertEqual(len(cat.records), 0)

    def test_default_registry_no_precise(self) -> None:
        reg = default_registry(_minimal_settings())
        self.assertNotIn("clause_lookup", reg.names())
        self.assertNotIn("table_lookup", reg.names())

    def test_kb_registry_default_not_gold(self) -> None:
        reg = KnowledgeBaseRegistry.default_gb39901(AEB_ROOT, catalog_mode="none")
        kb = reg.get("gb39901")
        self.assertEqual(len(kb.catalog.records), 0)

    def test_build_stack_default_tools(self) -> None:
        stack = build_stack(_minimal_settings())
        info = stack.describe()
        self.assertEqual(info["catalog_mode"], "none")
        self.assertFalse(info["enable_precise_lookup"])
        self.assertNotIn("clause_lookup", info["tools"])

    def test_unknown_precise_action_when_disabled(self) -> None:
        stack = build_stack(_minimal_settings())
        state = AgentState(question="test", policy="complex", max_steps=3)
        result = stack.registry.run("clause_lookup", state, {"clause": "6.11"})
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "unknown_tool")


if __name__ == "__main__":
    unittest.main()
