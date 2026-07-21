#!/usr/bin/env python3
"""Recompute evidence IDs and citation mappings in saved benchmark results."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from benchmark_common import EVIDENCE_PATH, load_jsonl, write_jsonl
from run_graphrag_benchmark import evidence_for_text, ranked_evidence


def remap_references(references: Any, items: list[dict[str, Any]]) -> list[str]:
    if not isinstance(references, list):
        return []
    reference_map = {
        f"R{index}": item.get("evidence_ids", [])
        for index, item in enumerate(items, 1)
    }
    return sorted(
        {
            evidence_id
            for reference in references
            for evidence_id in reference_map.get(str(reference), [])
        }
    )


def remap_record(record: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    updated = dict(record)
    items = []
    for item in record.get("retrieved_items", []):
        mapped = dict(item)
        mapped["evidence_ids"] = evidence_for_text(
            str(item.get("text", "")), str(item.get("file_path", "")), evidence
        )
        items.append(mapped)
    updated["retrieved_items"] = items
    ranked = ranked_evidence(items)
    updated["ranked_evidence_ids"] = ranked
    updated["retrieved_evidence_ids"] = sorted(set(ranked))

    prediction = dict(record.get("prediction", {}))
    references = prediction.get("reference_citations", [])
    prediction["citations"] = remap_references(references, items)
    raw_claims = prediction.get("claim_reference_citations", {})
    if isinstance(raw_claims, dict):
        prediction["claim_citations"] = {
            str(index): remap_references(value, items)
            for index, value in raw_claims.items()
        }
    updated["prediction"] = prediction
    updated["citations"] = prediction.get("citations", [])
    updated["evidence_mapping_version"] = "source_exact_hierarchical_clause_v3"
    return updated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evidence = load_jsonl(EVIDENCE_PATH)
    records = [remap_record(item, evidence) for item in load_jsonl(args.input)]
    write_jsonl(args.output, records)
    print(f"remapped rows={len(records)} output={args.output}")


if __name__ == "__main__":
    main()
