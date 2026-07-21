from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reg_harness.config import Settings
from reg_harness.tools.lightrag_retrieve import backfill_chunks_from_graph_hits
from reg_harness.types import EvidenceItem


class ChunkBackfillTests(unittest.TestCase):
    def test_backfill_promotes_shared_source_chunk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ws = "ws_test"
            store_dir = root / "data" / "rag_storage" / ws
            store_dir.mkdir(parents=True)
            chunk_id = "chunk-abc"
            body = "#### 6.11.3 车道内铁板误响应试验\n铁板尺寸..."
            (store_dir / "kv_store_text_chunks.json").write_text(
                json.dumps(
                    {
                        chunk_id: {
                            "content": body,
                            "file_path": "narrative_015.md",
                            "_id": chunk_id,
                        }
                    },
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
                chunk_backfill_enabled=True,
            )
            # Avoid live health overriding workspace
            settings._resolved_workspace = ws  # type: ignore[attr-defined]

            items = [
                EvidenceItem(
                    kind="relationship",
                    text="a --SPECIFIES--> b",
                    raw={"source_id": chunk_id},
                ),
                EvidenceItem(
                    kind="relationship",
                    text="c --SPECIFIES--> d",
                    raw={"source_id": chunk_id},
                ),
                EvidenceItem(
                    kind="entity",
                    text="e [clause]",
                    raw={"source_id": chunk_id},
                ),
            ]
            filled = backfill_chunks_from_graph_hits(settings, items, max_chunks=3)
            self.assertEqual(len(filled), 1)
            self.assertEqual(filled[0].kind, "chunk")
            self.assertIn("6.11.3", filled[0].text)
            self.assertEqual(filled[0].raw.get("cooccur"), 3)

    def test_backfill_can_disable(self) -> None:
        settings = Settings(
            aeb_root=Path("."),
            lightrag_url="http://127.0.0.1:9621",
            llm_host="",
            llm_api_key="",
            llm_model="t",
            llm_extra_body=None,
            chunk_backfill_enabled=False,
        )
        items = [
            EvidenceItem(
                kind="relationship",
                text="a --x--> b",
                raw={"source_id": "chunk-x"},
            )
        ]
        self.assertEqual(backfill_chunks_from_graph_hits(settings, items), [])


if __name__ == "__main__":
    unittest.main()
