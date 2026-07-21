"""Bag-side rerank + compact without domain topic dictionaries."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reg_harness.compact import compact_evidence, heuristic_score
from reg_harness.config import Settings
from reg_harness.types import EvidenceItem


def _settings(**kwargs) -> Settings:
    base = dict(
        aeb_root=Path("."),
        lightrag_url="http://127.0.0.1:9621",
        llm_host="",
        llm_api_key="",
        llm_model="dummy",
        llm_extra_body=None,
        bag_rerank_enabled=True,
        rerank_binding="aliyun",
        rerank_model="qwen3-rerank",
        rerank_host="https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank",
        rerank_api_key="test-key",
        min_rerank_score=0.0,
        bag_limit=20,
    )
    base.update(kwargs)
    return Settings(**base)


class BagRerankTests(unittest.TestCase):
    def test_no_topic_synonym_table(self) -> None:
        import reg_harness.compact as compact_mod

        self.assertFalse(hasattr(compact_mod, "_TOPIC_SYNONYMS"))

    def test_heuristic_fallback_no_settings(self) -> None:
        items = [
            EvidenceItem(kind="entity", text="noise entity"),
            EvidenceItem(kind="chunk", text="光照强度不小于 1000 lx"),
        ]
        out = compact_evidence(items, "最低光照强度是多少？", max_items=2)
        self.assertEqual(len(out), 2)
        # chunk baseline beats entity
        self.assertEqual(out[0].kind, "chunk")

    def test_rerank_orders_by_model_score(self) -> None:
        items = [
            EvidenceItem(kind="chunk", text="无关长文 " * 20),
            EvidenceItem(kind="relationship", text="光照强度不小于 1000 lx"),
            EvidenceItem(kind="chunk", text="另一段噪音"),
        ]
        settings = _settings()

        def fake_rerank(query, documents, **kwargs):
            # Prefer the short lux relation (index among non-empty docs)
            ranked = []
            for i, doc in enumerate(documents):
                score = 0.9 if "1000" in doc or "lx" in doc.lower() else 0.1
                ranked.append({"index": i, "relevance_score": score})
            ranked.sort(key=lambda r: r["relevance_score"], reverse=True)
            return ranked

        with patch("reg_harness.rerank.rerank_documents", side_effect=fake_rerank):
            out = compact_evidence(
                items,
                "6.5至6.7最低光照强度",
                max_items=3,
                settings=settings,
                query="光照强度 lx",
            )
        self.assertEqual(len(out), 3)
        # Text-primary: chunks occupy seats; high-score lux relation still kept.
        self.assertTrue(any("1000" in (i.text or "") for i in out))
        lux = next(i for i in out if "1000" in (i.text or ""))
        self.assertIsNotNone(lux.score)
        self.assertGreaterEqual(lux.score or 0, 0.8)

    def test_rerank_failure_falls_back(self) -> None:
        items = [
            EvidenceItem(kind="entity", text="x"),
            EvidenceItem(kind="chunk", text="重要原文条款 5.4"),
        ]
        settings = _settings()

        with patch(
            "reg_harness.rerank.rerank_documents",
            side_effect=RuntimeError("network down"),
        ):
            out = compact_evidence(
                items, "5.4 要求", max_items=2, settings=settings
            )
        self.assertEqual(out[0].kind, "chunk")

    def test_heuristic_score_no_chapter_boost(self) -> None:
        # "第7章" alone should not beat a plain chunk about 说明书 unless question terms hit
        a = EvidenceItem(kind="chunk", text="第7章 目录")
        b = EvidenceItem(kind="chunk", text="说明书应包含系统功能描述")
        q = "说明书要写什么"
        # both get focus hits potentially; ensure no special chapter dictionary path
        sa = heuristic_score(a, q)
        sb = heuristic_score(b, q)
        self.assertGreaterEqual(sb, sa)


if __name__ == "__main__":
    unittest.main()
