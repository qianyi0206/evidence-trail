from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

AEB_ROOT = Path(__file__).resolve().parents[2]
KG_SCHEMA_PATH = AEB_ROOT / "config" / "gb_39901_2025_schema.yml"


def load_kg_contract(
    path: Path = KG_SCHEMA_PATH,
) -> tuple[set[str], dict[str, tuple[set[str], set[str]]]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Invalid KG schema root: {path}")
    entity_types = {
        str(item)
        for item in payload.get("entity_types", [])
        if str(item).strip()
    }
    raw_relations = payload.get("relation_definitions", {})
    if not entity_types or not isinstance(raw_relations, dict):
        raise RuntimeError(f"Incomplete KG schema contract: {path}")
    relations: dict[str, tuple[set[str], set[str]]] = {}
    for relation, definition in raw_relations.items():
        if not isinstance(definition, dict):
            raise RuntimeError(f"Invalid relation definition {relation}: {definition!r}")
        sources = {str(item) for item in definition.get("source", [])}
        targets = {str(item) for item in definition.get("target", [])}
        if not sources or not targets:
            raise RuntimeError(f"Relation {relation} has empty endpoint types")
        unknown = (sources | targets) - entity_types
        if unknown:
            raise RuntimeError(
                f"Relation {relation} references unknown types: {sorted(unknown)}"
            )
        relations[str(relation)] = (sources, targets)
    return entity_types, relations


KG_SCHEMA_TYPES, KG_RELATION_ENDPOINTS = load_kg_contract()


def graph_edge_is_schema_legal(
    edge: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
) -> bool:
    relation = str(edge.get("relation", ""))
    if relation not in KG_RELATION_ENDPOINTS:
        return False
    source = nodes.get(str(edge.get("source")))
    target = nodes.get(str(edge.get("target")))
    if source is None or target is None:
        return False
    allowed_sources, allowed_targets = KG_RELATION_ENDPOINTS[relation]
    return (
        source.get("type") in allowed_sources
        and target.get("type") in allowed_targets
    )


def evidence_source_ids(
    evidence_ids: list[str],
    evidence: dict[str, dict[str, Any]],
) -> set[str]:
    return {
        str(evidence[item].get("source_id"))
        for item in evidence_ids
        if item in evidence
    }


def question_source_ids(question: dict[str, Any]) -> set[str]:
    return {
        "gb39901"
        if str(item).startswith("gb39901:")
        else str(item).split(":", 1)[0]
        for item in question.get("gold_evidence_ids", [])
    }
