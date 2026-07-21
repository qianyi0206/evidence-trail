#!/usr/bin/env python3
"""Export a LightRAG workspace into the benchmark's node/edge JSONL contract."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from benchmark_common import AEB_ROOT, EVIDENCE_PATH, load_jsonl, normalize_text, write_jsonl


RELATION_RE = re.compile(r"relation_type\s*=\s*([A-Z_]+)", re.IGNORECASE)
CLAUSE_RE = re.compile(r"(?:来源条款|source_clause)\s*[=:]\s*([^；;\n<]+)", re.IGNORECASE)
VALUE_RE = re.compile(
    r"operator\s*=\s*([A-Z_<>≤≥]+).*?value\s*=\s*(-?\d+(?:\.\d+)?).*?unit\s*=\s*([^；;。\n]+)",
    re.IGNORECASE,
)


def evidence_index() -> list[dict[str, Any]]:
    return load_jsonl(EVIDENCE_PATH)


def map_evidence_ids(text: str, file_path: str, evidence: list[dict[str, Any]]) -> list[str]:
    matched: list[str] = []
    normalized_text = normalize_text(text)
    table_match = re.search(r"(?:__table_|table[_-]?)(a_)?(\d+)", file_path, re.IGNORECASE)
    clauses = {match.group(1).strip() for match in CLAUSE_RE.finditer(text or "")}
    for record in evidence:
        locator = record.get("locator", {})
        record_table = str(locator.get("table", "")).lower().replace(".", "_")
        if table_match and record_table:
            prefix = "a_" if table_match.group(1) else ""
            if record_table.replace(" ", "_") == f"{prefix}{table_match.group(2)}":
                matched.append(record["id"])
                continue
        clause_values = []
        if locator.get("clause"):
            clause_values.append(str(locator["clause"]))
        clause_values.extend(str(item) for item in locator.get("clauses", []))
        if any(
            clause == candidate
            or clause.startswith(candidate + ".")
            or candidate.startswith(clause + ".")
            for clause in clauses
            for candidate in clause_values
        ):
            matched.append(record["id"])
            continue
        excerpt = normalize_text(record.get("source_excerpt", ""))
        if excerpt and len(excerpt) >= 20 and (
            excerpt in normalized_text or normalized_text in excerpt
        ):
            matched.append(record["id"])
    return sorted(set(matched))


def numeric_tuples(text: str) -> list[dict[str, Any]]:
    tuples = []
    for operator, value, unit in VALUE_RE.findall(text or ""):
        tuples.append(
            {
                "operator": operator.upper(),
                "value": float(value),
                "unit": unit.strip(),
                "condition": text.split("qualifiers=", 1)[-1].strip("。 ") if "qualifiers=" in text else "",
            }
        )
    return tuples


def local_export(storage_root: Path, workspace: str) -> list[dict[str, Any]]:
    root = storage_root / workspace
    entity_path = root / "vdb_entities.json"
    relation_path = root / "vdb_relationships.json"
    if not entity_path.is_file() or not relation_path.is_file():
        raise RuntimeError(f"Missing LightRAG vector stores under {root}")
    evidence = evidence_index()
    entities = json.loads(entity_path.read_text(encoding="utf-8")).get("data", [])
    relationships = json.loads(relation_path.read_text(encoding="utf-8")).get("data", [])
    records: list[dict[str, Any]] = []
    names: set[str] = set()
    for item in entities:
        name = str(item.get("entity_name", "")).strip()
        if not name or name in names:
            continue
        names.add(name)
        description = str(item.get("content", ""))
        file_path = str(item.get("file_path", ""))
        records.append(
            {
                "kind": "node",
                "id": name,
                "name": name,
                "type": item.get("entity_type") or "Unknown",
                "description": description,
                "aliases": [],
                "properties": {"source_id": item.get("source_id", ""), "file_path": file_path},
                "evidence_ids": map_evidence_ids(description, file_path, evidence),
                "numeric_condition_tuples": numeric_tuples(description),
                "schema_valid": item.get("entity_type") not in {None, "", "UNKNOWN", "Unknown"},
            }
        )
    for index, item in enumerate(relationships, 1):
        source = str(item.get("src_id", "")).strip()
        target = str(item.get("tgt_id", "")).strip()
        if not source or not target:
            continue
        description = str(item.get("content", ""))
        first_line = description.splitlines()[0].strip().upper() if description else ""
        match = RELATION_RE.search(description)
        relation = match.group(1).upper() if match else first_line
        file_path = str(item.get("file_path", ""))
        records.append(
            {
                "kind": "edge",
                "id": str(item.get("__id__") or f"edge:{index:06d}"),
                "source": source,
                "target": target,
                "relation": relation or "UNMAPPED",
                "description": description,
                "properties": {"source_id": item.get("source_id", ""), "file_path": file_path},
                "evidence_ids": map_evidence_ids(description, file_path, evidence),
                "schema_valid": relation not in {"", "UNMAPPED"},
            }
        )
    return records


def live_export(profile_env: str | None) -> tuple[str, list[dict[str, Any]]]:
    scripts_dir = AEB_ROOT / "scripts"
    sys.path.insert(0, str(scripts_dir))
    if profile_env:
        os.environ["AEB_PROFILE_ENV"] = profile_env
    from common import load_env, neo4j_query, safe_workspace  # type: ignore

    env = load_env()
    workspace = safe_workspace(env)
    label = f"`{workspace}`"
    evidence = evidence_index()
    node_rows = neo4j_query(
        env,
        f"MATCH (n:{label}) RETURN n.entity_id, n.entity_type, n.description, "
        "n.file_path, n.source_id, n.schema_valid, n.canonical_name ORDER BY n.entity_id",
    )
    edge_rows = neo4j_query(
        env,
        f"MATCH (a:{label})-[r:DIRECTED]->(b:{label}) RETURN elementId(r), "
        "coalesce(r.logical_source,a.entity_id), coalesce(r.logical_target,b.entity_id), "
        "r.relation_type, r.description, r.file_path, r.source_id, r.schema_valid "
        "ORDER BY a.entity_id,b.entity_id",
    )
    records: list[dict[str, Any]] = []
    for name, entity_type, description, file_path, source_id, schema_valid, canonical in node_rows:
        text = str(description or "")
        path = str(file_path or "")
        records.append(
            {
                "kind": "node", "id": name, "name": canonical or name,
                "type": entity_type or "Unknown", "description": text,
                "aliases": [] if not canonical or canonical == name else [name],
                "properties": {"source_id": source_id or "", "file_path": path},
                "evidence_ids": map_evidence_ids(text, path, evidence),
                "numeric_condition_tuples": numeric_tuples(text),
                "schema_valid": None if schema_valid is None else bool(schema_valid),
            }
        )
    for edge_id, source, target, relation, description, file_path, source_id, schema_valid in edge_rows:
        text = str(description or "")
        path = str(file_path or "")
        records.append(
            {
                "kind": "edge", "id": edge_id, "source": source, "target": target,
                "relation": relation or "UNMAPPED", "description": text,
                "properties": {"source_id": source_id or "", "file_path": path},
                "evidence_ids": map_evidence_ids(text, path, evidence),
                "schema_valid": None if schema_valid is None else bool(schema_valid),
            }
        )
    return workspace, records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", help="LightRAG workspace for local vector-store export")
    parser.add_argument("--storage-root", type=Path, default=AEB_ROOT / "data" / "rag_storage")
    parser.add_argument("--live", action="store_true", help="export typed graph directly from Neo4j")
    parser.add_argument("--profile-env", help="profile file relative to demo/aeb, e.g. .env.gb39901_v4")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.live:
        workspace, records = live_export(args.profile_env)
    else:
        if not args.workspace:
            raise SystemExit("--workspace is required unless --live is used")
        workspace = args.workspace
        records = local_export(args.storage_root, workspace)
    write_jsonl(args.output, records)
    nodes = sum(item["kind"] == "node" for item in records)
    edges = sum(item["kind"] == "edge" for item in records)
    print(f"exported workspace={workspace} nodes={nodes} edges={edges} output={args.output}")


if __name__ == "__main__":
    main()
