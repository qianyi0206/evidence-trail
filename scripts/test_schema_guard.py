#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import yaml

from common import ROOT


sys.path.insert(0, str(ROOT / "lightrag_custom"))
from schema_guard import RELATION_ENDPOINTS, filter_extraction_result, reset_type_cache


def entity(entity_type: str) -> list[dict]:
    return [{"entity_type": entity_type, "description": "test"}]


def edge(source: str, target: str, relation: str) -> list[dict]:
    return [
        {
            "src_id": source,
            "tgt_id": target,
            "keywords": relation,
            "description": f"relation_type={relation}；source_clause=test；evidence=test；",
        }
    ]


def main() -> None:
    schema = yaml.safe_load(
        (ROOT / "config" / "gb_39901_2025_schema.yml").read_text(encoding="utf-8")
    )
    expected = {
        relation: (set(definition["source"]), set(definition["target"]))
        for relation, definition in schema["relation_definitions"].items()
    }
    if RELATION_ENDPOINTS != expected:
        raise RuntimeError("Runtime schema guard is not identical to the YAML relation contract")

    reset_type_cache()
    nodes = {
        "R1": entity("requirement"),
        "R2": entity("Requirement"),
        "T1": entity("TestScenario"),
        "T2": entity("Threshold"),
        "C1": entity("Clause"),
        "T3": entity("Threshold"),
        "O1": entity("Organization"),
        "M1": entity("Metric"),
        "D1": entity("Condition"),
    }
    edges = {
        ("R1", "T1"): edge("R1", "T1", "APPLIES_TO"),
        ("C1", "T2"): edge("C1", "T2", "HAS_THRESHOLD"),
        ("R1", "O1"): edge("R1", "O1", "APPLIES_TO"),
        ("R2", "T3"): edge("R2", "T3", "HAS_THRESHOLD"),
        ("T2", "R2"): edge("T2", "R2", "HAS_THRESHOLD"),
        ("M1", "D1"): edge("M1", "D1", "HAS_PARAMETER"),
    }
    filtered, stats = filter_extraction_result(nodes, edges, "unit-test")
    actual = {
        key: values[0]["keywords"]
        for key, values in filtered.items()
    }
    # Keep only declared relations that already match endpoints (or reverse).
    # Do not invent a relation from type-pair cardinality.
    expected_edges = {
        ("R2", "T3"): "HAS_THRESHOLD",  # kept
        ("R2", "T2"): "HAS_THRESHOLD",  # reversed T2->R2
    }
    if actual != expected_edges:
        raise RuntimeError(f"Unexpected filtered edge set: {actual}")
    if stats != {
        "kept": 1,
        "repaired": 0,
        "reversed": 1,
        "repaired_reversed": 0,
        "dropped": 4,
    }:
        raise RuntimeError(f"Unexpected guard statistics: {stats}")

    for (source, target), relation in actual.items():
        source_type = nodes[source][0]["entity_type"].strip().casefold()
        target_type = nodes[target][0]["entity_type"].strip().casefold()
        allowed_sources, allowed_targets = RELATION_ENDPOINTS[relation]
        if source_type not in {item.casefold() for item in allowed_sources}:
            raise RuntimeError(f"Invalid guarded source endpoint: {source} {relation}")
        if target_type not in {item.casefold() for item in allowed_targets}:
            raise RuntimeError(f"Invalid guarded target endpoint: {relation} {target}")
    print("schema-guard OK (42 relation contracts; keep/reverse/drop verified; no invent-repair)")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"schema-guard FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
