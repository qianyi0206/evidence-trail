"""P0 assembly: budgets expand, text-primary bag, sectioned compose, numeric normalize."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reg_harness.compact import apply_text_primary_quota, compact_evidence
from reg_harness.config import Settings
from reg_harness.guards import (
    collect_context_numbers,
    normalize_numeric_text,
    validate_final_answer,
)
from reg_harness.tools.lightrag_retrieve import (
    backfill_chunks_from_graph_hits,
    split_source_ids,
)
from reg_harness.types import AgentState, EvidenceItem


class SourceIdExpandTests(unittest.TestCase):
    def test_split_sep(self) -> None:
        parts = split_source_ids("chunk-a<SEP>chunk-b<SEP>chunk-c")
        self.assertEqual(parts, ["chunk-a", "chunk-b", "chunk-c"])

    def test_backfill_splits_multi_source_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ws = "ws_sep"
            store_dir = root / "data" / "rag_storage" / ws
            store_dir.mkdir(parents=True)
            store = {
                "chunk-a": {"content": "全文A 含 2 000 lx", "file_path": "a.md"},
                "chunk-b": {"content": "全文B", "file_path": "b.md"},
            }
            (store_dir / "kv_store_text_chunks.json").write_text(
                json.dumps(store, ensure_ascii=False), encoding="utf-8"
            )
            settings = Settings(
                aeb_root=root,
                lightrag_url="http://127.0.0.1:9621",
                llm_host="",
                llm_api_key="",
                llm_model="t",
                llm_extra_body=None,
                workspace=ws,
                chunk_backfill_enabled=True,
            )
            settings._resolved_workspace = ws  # type: ignore[attr-defined]
            items = [
                EvidenceItem(
                    kind="relationship",
                    text="half triple 1 000 only",
                    raw={"source_id": "chunk-a<SEP>chunk-b"},
                )
            ]
            filled = backfill_chunks_from_graph_hits(settings, items, max_chunks=4)
            texts = {f.text for f in filled}
            self.assertIn("全文A 含 2 000 lx", texts)
            self.assertIn("全文B", texts)

    def test_skip_already_returned_chunk_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ws = "ws_skip"
            store_dir = root / "data" / "rag_storage" / ws
            store_dir.mkdir(parents=True)
            (store_dir / "kv_store_text_chunks.json").write_text(
                json.dumps(
                    {"chunk-x": {"content": "should not duplicate", "file_path": "x.md"}},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            settings = Settings(
                aeb_root=root,
                lightrag_url="http://127.0.0.1:9621",
                llm_host="",
                llm_api_key="",
                llm_model="t",
                llm_extra_body=None,
                workspace=ws,
            )
            settings._resolved_workspace = ws  # type: ignore[attr-defined]
            items = [
                EvidenceItem(
                    kind="chunk",
                    text="should not duplicate",
                    raw={"id": "chunk-x"},
                ),
                EvidenceItem(
                    kind="entity",
                    text="e",
                    raw={"source_id": "chunk-x"},
                ),
            ]
            filled = backfill_chunks_from_graph_hits(settings, items)
            self.assertEqual(filled, [])


class TextPrimaryQuotaTests(unittest.TestCase):
    def test_chunks_dominate_bag(self) -> None:
        items = []
        for i in range(10):
            items.append(
                EvidenceItem(kind="entity", text=f"ent{i}", score=0.99 - i * 0.01)
            )
        for i in range(10):
            items.append(
                EvidenceItem(kind="relationship", text=f"rel{i}", score=0.98 - i * 0.01)
            )
        for i in range(8):
            items.append(
                EvidenceItem(kind="chunk", text=f"chunk body {i} " * 5, score=0.5)
            )
        out = apply_text_primary_quota(
            items, max_items=20, max_entities=5, max_relations=5
        )
        n_chunk = sum(1 for i in out if i.kind == "chunk")
        n_ent = sum(1 for i in out if i.kind == "entity")
        n_rel = sum(1 for i in out if i.kind == "relationship")
        self.assertGreaterEqual(n_chunk, 8)
        self.assertLessEqual(n_ent, 5)
        self.assertLessEqual(n_rel, 5)
        self.assertEqual(out[0].kind, "chunk")

    def test_precise_catalog_evidence_is_not_dropped(self) -> None:
        items = [
            EvidenceItem(kind="chunk", text="unrelated chunk one", score=0.9),
            EvidenceItem(kind="chunk", text="unrelated chunk two", score=0.8),
            EvidenceItem(kind="catalog", text="precise table row", score=0.1),
        ]
        out = apply_text_primary_quota(
            items, max_items=2, max_entities=0, max_relations=0
        )
        self.assertEqual(out[0].kind, "catalog")
        self.assertIn("precise table row", [item.text for item in out])


class ComposeSectionTests(unittest.TestCase):
    def test_compose_sections_order(self) -> None:
        state = AgentState(question="q")
        state.evidence = [
            EvidenceItem(kind="entity", text="E entity only"),
            EvidenceItem(kind="relationship", text="R relation only"),
            EvidenceItem(kind="chunk", text="C chunk full 2 000 lx"),
        ]
        text = state.evidence_text(for_compose=True)
        self.assertIn("## Text units", text)
        self.assertIn("## Relations", text)
        self.assertIn("## Entities", text)
        pos_t = text.index("## Text units")
        pos_r = text.index("## Relations")
        pos_e = text.index("## Entities")
        self.assertLess(pos_t, pos_r)
        self.assertLess(pos_r, pos_e)
        self.assertLess(text.index("C chunk"), text.index("R relation"))

    def test_catalog_is_rendered_as_text_unit(self) -> None:
        state = AgentState(
            question="q",
            evidence=[EvidenceItem(kind="catalog", text="precise catalog row")],
        )
        text = state.evidence_text(for_compose=True)
        self.assertIn("## Text units", text)
        self.assertIn("kind=catalog", text)


class NumericNormalizeTests(unittest.TestCase):
    def test_spaced_thousands(self) -> None:
        self.assertIn("1000", normalize_numeric_text("不小于1 000 lx"))
        self.assertIn("2000", normalize_numeric_text("不小于2 000 lx"))
        self.assertEqual(normalize_numeric_text("1 000"), "1000")

    def test_guard_accepts_spaced_context(self) -> None:
        state = AgentState(question="光照")
        state.evidence.append(
            EvidenceItem(
                kind="chunk",
                text="g）进行6.5～6.7试验时，光照强度不小于1 000 lx，其他试验光照强度不小于2 000 lx。",
            )
        )
        nums = collect_context_numbers(state.evidence)
        self.assertIn("1000", nums)
        self.assertIn("2000", nums)
        checked = validate_final_answer(
            state,
            {
                "answerable": True,
                "answer": {
                    "a": "1000 lx",
                    "b": "2000 lx",
                },
                "claims": ["1000", "2000"],
                "citations": ["E1"],
                "reason": "ok",
            },
        )
        self.assertTrue(checked.get("answerable"))
        self.assertNotIn(
            "forced_refusal_ungrounded_numeric",
            checked.get("validation_flags") or [],
        )


if __name__ == "__main__":
    unittest.main()
