#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import httpx
import yaml

from common import (
    ROOT,
    api_headers,
    lightrag_url,
    load_env,
    neo4j_query,
    safe_workspace,
    workspace_state_path,
    write_json_atomic,
)


SCHEMA_PATH = ROOT / "config" / "gb_39901_2025_schema.yml"
SOURCE_CLAUSE_RE = re.compile(r"(?:来源条款|source_clause)\s*[=:]\s*([^；;\n]+)", re.IGNORECASE)
RELATION_TYPE_RE = re.compile(r"relation_type\s*=\s*([A-Z_]+)")

RELATION_ALIASES = {
    "USES_SIGNAL": "HAS_SIGNAL",
}

EXPLICIT_ALIASES = {
    ("system", "aebs"): "自动紧急制动系统（AEBS）",
    ("system", "aeb系统"): "自动紧急制动系统（AEBS）",
    ("system", "自动紧急制动系统"): "自动紧急制动系统（AEBS）",
    ("vehiclecategory", "m1"): "M1类汽车",
    ("vehiclecategory", "m1类汽车"): "M1类汽车",
    ("vehiclecategory", "n1"): "N1类汽车",
    ("vehiclecategory", "n1类汽车"): "N1类汽车",
    ("standard", "gb399012025"): "GB 39901-2025",
    ("standard", "gb/t399012021"): "GB/T 39901-2021",
}

_REPAIRED_RELATIONS: list[dict[str, str]] = []
_REPAIR_ATTEMPTS: set[tuple[str, str]] = set()
_MERGED_ALIASES: list[dict[str, Any]] = []
_MERGE_ATTEMPTS: set[tuple[str, str]] = set()
_AUDIT_LOADED_WORKSPACES: set[str] = set()


def normalized_token(value: str) -> str:
    return re.sub(r"[\s_—–-]+", "", value).lower()


def canonical_name(entity_type: str, name: str) -> str:
    key = (entity_type.lower(), normalized_token(name))
    return EXPLICIT_ALIASES.get(key, name.strip())


def canonical_id(schema_type: str, name: str) -> str:
    digest = hashlib.sha1(f"{schema_type}\0{name}".encode("utf-8")).hexdigest()[:16]
    return f"GB39901-2025::{schema_type}::{digest}"


def source_clause(description: str) -> str | None:
    match = SOURCE_CLAUSE_RE.search(description or "")
    return match.group(1).strip() if match else None


def relation_type(keywords: str, description: str, allowed: set[str]) -> str | None:
    tokens = re.split(r"(?:,|，|<SEP>|\s)+", (keywords or "").upper())
    exact = [RELATION_ALIASES.get(token, token) for token in tokens]
    exact = [token for token in exact if token in allowed]
    if exact:
        return exact[0]
    match = RELATION_TYPE_RE.search(description or "")
    if match:
        candidate = RELATION_ALIASES.get(match.group(1), match.group(1))
        if candidate in allowed:
            return candidate
    return None


def description_with_relation_type(description: str, new_type: str) -> str:
    if RELATION_TYPE_RE.search(description or ""):
        return RELATION_TYPE_RE.sub(
            f"relation_type={new_type}", description, count=1
        )
    return f"relation_type={new_type}；{description or ''}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Annotate a LightRAG Neo4j graph with GB 39901 schema metadata")
    parser.add_argument("--apply", action="store_true", help="Write non-destructive schema annotations to Neo4j")
    parser.add_argument(
        "--repair-invalid",
        action="store_true",
        help="Repair a type-invalid relation only when the schema has exactly one compatible endpoint contract",
    )
    parser.add_argument(
        "--merge-explicit-aliases",
        action="store_true",
        help="Merge only aliases declared in EXPLICIT_ALIASES through the LightRAG graph API",
    )
    parser.add_argument("--strict", action="store_true", help="Fail if unmapped or type-invalid relations remain")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env = load_env()
    workspace = safe_workspace(env)
    report_path = workspace_state_path(env, "schema_report")
    if workspace not in _AUDIT_LOADED_WORKSPACES and report_path.exists():
        previous = json.loads(report_path.read_text(encoding="utf-8"))
        _REPAIRED_RELATIONS.extend(previous.get("repaired_relations", []))
        _MERGED_ALIASES.extend(previous.get("merged_aliases", []))
        _AUDIT_LOADED_WORKSPACES.add(workspace)
    label = f"`{workspace}`"
    schema = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    allowed_relations = set(schema["relations_of_interest"])
    definitions = schema["relation_definitions"]
    schema_types = {item.lower(): item for item in schema["entity_types"]}

    node_rows = neo4j_query(
        env,
        f"MATCH (n:{label}) RETURN elementId(n), n.entity_id, n.entity_type, n.description ORDER BY n.entity_id",
    )
    edge_rows = neo4j_query(
        env,
        f"MATCH (a:{label})-[r:DIRECTED]->(b:{label}) "
        "RETURN elementId(r), a.entity_id, a.entity_type, b.entity_id, b.entity_type, "
        "r.keywords, r.description ORDER BY a.entity_id, b.entity_id",
    )
    if not node_rows or not edge_rows:
        raise RuntimeError(f"Workspace {workspace} has no graph data")

    node_updates = []
    alias_groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    invalid_node_types = []
    for element_id, name, raw_type, description in node_rows:
        raw_type = (raw_type or "").strip()
        schema_type = schema_types.get(raw_type.lower())
        canonical = canonical_name(raw_type, name)
        error = "" if schema_type else f"unknown_entity_type:{raw_type or '<empty>'}"
        if error:
            invalid_node_types.append({"entity": name, "entity_type": raw_type})
            schema_type = raw_type or "Unknown"
        alias_groups[(schema_type, canonical)].append(name)
        node_updates.append(
            {
                "element_id": element_id,
                "canonical_name": canonical,
                "canonical_id": canonical_id(schema_type, canonical),
                "schema_type": schema_type,
                "schema_valid": not error,
                "schema_error": error,
                "source_clause": source_clause(description or ""),
            }
        )

    relation_updates = []
    relation_counts: Counter[str] = Counter()
    invalid_relations = []
    unmapped_relations = []
    repair_candidates = []
    for element_id, src, src_type_raw, tgt, tgt_type_raw, keywords, description in edge_rows:
        mapped = relation_type(keywords or "", description or "", allowed_relations)
        src_type = schema_types.get((src_type_raw or "").lower())
        tgt_type = schema_types.get((tgt_type_raw or "").lower())
        logical_source = src
        logical_target = tgt
        reversed_storage = False
        error = ""
        if not mapped:
            error = "unmapped_relation_type"
            unmapped_relations.append({"source": src, "target": tgt, "keywords": keywords})
        elif not src_type or not tgt_type:
            error = "unknown_endpoint_type"
        else:
            definition = definitions[mapped]
            forward_ok = src_type in definition["source"] and tgt_type in definition["target"]
            reverse_ok = tgt_type in definition["source"] and src_type in definition["target"]
            if not forward_ok and reverse_ok:
                logical_source, logical_target = tgt, src
                reversed_storage = True
            elif not forward_ok:
                error = f"invalid_endpoints:{src_type}->{tgt_type}"
                endpoint_candidates = []
                for candidate, candidate_definition in definitions.items():
                    if (
                        src_type in candidate_definition["source"]
                        and tgt_type in candidate_definition["target"]
                    ):
                        endpoint_candidates.append((candidate, False))
                    if (
                        tgt_type in candidate_definition["source"]
                        and src_type in candidate_definition["target"]
                    ):
                        endpoint_candidates.append((candidate, True))
                if len(endpoint_candidates) == 1:
                    suggested_type, suggested_reversed = endpoint_candidates[0]
                    repair_candidates.append(
                        {
                            "source": src,
                            "target": tgt,
                            "old_relation_type": mapped,
                            "new_relation_type": suggested_type,
                            "storage_direction_reversed": suggested_reversed,
                            "description": description or "",
                        }
                    )
        if mapped:
            relation_counts[mapped] += 1
        if error and mapped:
            invalid_relations.append(
                {"source": src, "target": tgt, "relation_type": mapped, "error": error}
            )
        relation_updates.append(
            {
                "element_id": element_id,
                "relation_type": mapped or "UNMAPPED",
                "schema_valid": not error,
                "schema_error": error,
                "logical_source": logical_source,
                "logical_target": logical_target,
                "storage_direction_reversed": reversed_storage,
                "source_clause": source_clause(description or ""),
            }
        )

    if args.repair_invalid and repair_candidates:
        if not args.apply:
            raise RuntimeError("--repair-invalid requires --apply")
        repaired_this_pass = 0
        for repair in repair_candidates:
            pair = (repair["source"], repair["target"])
            if pair in _REPAIR_ATTEMPTS:
                continue
            _REPAIR_ATTEMPTS.add(pair)
            new_type = repair["new_relation_type"]
            response = httpx.post(
                lightrag_url(env, "/graph/relation/edit"),
                headers=api_headers(env),
                json={
                    "source_id": repair["source"],
                    "target_id": repair["target"],
                    "updated_data": {
                        "keywords": new_type,
                        "description": description_with_relation_type(
                            repair["description"], new_type
                        ),
                    },
                },
                timeout=120,
            )
            response.raise_for_status()
            summary = {
                key: str(repair[key])
                for key in (
                    "source",
                    "target",
                    "old_relation_type",
                    "new_relation_type",
                    "storage_direction_reversed",
                )
            }
            _REPAIRED_RELATIONS.append(summary)
            repaired_this_pass += 1
        if repaired_this_pass:
            print(
                f"postprocess repaired={repaired_this_pass} type-invalid relation(s) "
                "through the LightRAG graph API; revalidating"
            )
            return main()

    isolated_rows = neo4j_query(
        env,
        f"MATCH (n:{label}) WHERE NOT (n)--() RETURN n.entity_id, n.entity_type ORDER BY n.entity_id",
    )
    duplicate_candidates = [
        {"schema_type": key[0], "canonical_name": key[1], "entities": sorted(names)}
        for key, names in alias_groups.items()
        if len(set(names)) > 1
    ]

    if args.merge_explicit_aliases and duplicate_candidates:
        if not args.apply:
            raise RuntimeError("--merge-explicit-aliases requires --apply")
        merged_this_pass = 0
        for group in duplicate_candidates:
            schema_type = group["schema_type"]
            canonical = group["canonical_name"]
            entities = group["entities"]
            if not all(
                name == canonical
                or (schema_type.lower(), normalized_token(name)) in EXPLICIT_ALIASES
                for name in entities
            ):
                continue
            target = canonical if canonical in entities else max(
                entities, key=lambda name: (len(name), name)
            )
            sources = [name for name in entities if name != target]
            attempt = (schema_type, canonical)
            if not sources or attempt in _MERGE_ATTEMPTS:
                continue
            _MERGE_ATTEMPTS.add(attempt)
            response = httpx.post(
                lightrag_url(env, "/graph/entities/merge"),
                headers=api_headers(env),
                json={
                    "entities_to_change": sources,
                    "entity_to_change_into": target,
                },
                timeout=180,
            )
            response.raise_for_status()
            _MERGED_ALIASES.append(
                {
                    "schema_type": schema_type,
                    "canonical_name": canonical,
                    "target_entity": target,
                    "merged_entities": sources,
                }
            )
            merged_this_pass += 1
        if merged_this_pass:
            print(
                f"postprocess merged={merged_this_pass} explicit alias group(s) "
                "through the LightRAG graph API; revalidating"
            )
            return main()

    if args.apply:
        neo4j_query(
            env,
            "UNWIND $updates AS u MATCH (n) WHERE elementId(n)=u.element_id "
            "SET n.canonical_name=u.canonical_name, n.canonical_id=u.canonical_id, "
            "n.schema_type=u.schema_type, n.schema_valid=u.schema_valid, n.schema_error=u.schema_error, "
            "n.source_clause=coalesce(u.source_clause, n.source_clause) RETURN count(n)",
            {"updates": node_updates},
        )
        neo4j_query(
            env,
            "UNWIND $updates AS u MATCH ()-[r:DIRECTED]->() WHERE elementId(r)=u.element_id "
            "SET r.relation_type=u.relation_type, r.schema_valid=u.schema_valid, r.schema_error=u.schema_error, "
            "r.logical_source=u.logical_source, r.logical_target=u.logical_target, "
            "r.storage_direction_reversed=u.storage_direction_reversed, "
            "r.source_clause=coalesce(u.source_clause, r.source_clause) RETURN count(r)",
            {"updates": relation_updates},
        )

    report: dict[str, Any] = {
        "workspace": workspace,
        "applied": args.apply,
        "nodes": len(node_rows),
        "relations": len(edge_rows),
        "valid_nodes": len(node_rows) - len(invalid_node_types),
        "invalid_node_types": invalid_node_types,
        "mapped_relations": sum(relation_counts.values()),
        "unmapped_relations": unmapped_relations,
        "invalid_relations": invalid_relations,
        "repaired_relations": list(_REPAIRED_RELATIONS),
        "merged_aliases": list(_MERGED_ALIASES),
        "relation_type_counts": dict(relation_counts.most_common()),
        "isolated_nodes": [{"entity": row[0], "entity_type": row[1]} for row in isolated_rows],
        "duplicate_candidates": duplicate_candidates,
        "normalization_note": "canonical_name is annotated; duplicate nodes are not merged automatically.",
        "isolation_note": "isolated nodes are reported; no evidence-free edges are created automatically.",
    }
    write_json_atomic(report_path, report)
    print(
        "postprocess "
        f"{'APPLIED' if args.apply else 'DRY-RUN'} nodes={len(node_rows)} relations={len(edge_rows)} "
        f"mapped={report['mapped_relations']} unmapped={len(unmapped_relations)} "
        f"invalid={len(invalid_relations)} isolated={len(isolated_rows)} "
        f"duplicates={len(duplicate_candidates)} report={report_path}"
    )
    if args.strict and (invalid_node_types or unmapped_relations or invalid_relations):
        raise RuntimeError("Strict schema validation failed; inspect the schema report")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"postprocess FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
