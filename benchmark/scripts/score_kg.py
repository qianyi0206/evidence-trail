#!/usr/bin/env python3
"""Score extracted knowledge graphs against task and audit gold graphs."""

from __future__ import annotations

import argparse
import itertools
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from benchmark_common import (
    AUDIT_PATH,
    GRAPH_PATH,
    QUESTIONS_PATH,
    claim_similarity,
    index_by_id,
    load_jsonl,
    normalize_name,
    normalize_text,
    precision_recall_f1,
    safe_float,
    write_json,
)


RELATION_ALIASES = {"USES_SIGNAL": "HAS_SIGNAL"}
OPERATOR_ALIASES = {"LTE": "<=", "GTE": ">=", "LT": "<", "GT": ">", "EQ": "="}


def canonical_relation(value: Any) -> str:
    relation = str(value or "").strip().upper()
    return RELATION_ALIASES.get(relation, relation)


def canonical_nodes(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for node in records:
        key = f"{normalize_name(node.get('type'))}::{normalize_name(node.get('name'))}"
        if key not in result:
            result[key] = node
    return result


def node_similarity(gold: dict[str, Any], predicted: dict[str, Any]) -> float:
    gold_names = [gold.get("name", ""), *gold.get("aliases", [])]
    predicted_names = [predicted.get("name", predicted.get("id", "")), *predicted.get("aliases", [])]
    best = 0.0
    for left in gold_names:
        for right in predicted_names:
            if normalize_name(left) == normalize_name(right):
                return 1.0
            if normalize_name(left) in normalize_name(right) or normalize_name(right) in normalize_name(left):
                best = max(best, 0.9)
            best = max(best, claim_similarity(left, right))
    return best


def match_nodes(
    gold_nodes: list[dict[str, Any]],
    predicted_nodes: list[dict[str, Any]],
    threshold: float,
) -> tuple[dict[str, str], dict[str, str], list[tuple[str, str, float]]]:
    candidates = []
    for gold in gold_nodes:
        for predicted in predicted_nodes:
            score = node_similarity(gold, predicted)
            if score >= threshold:
                candidates.append((score, gold["id"], predicted["id"]))
    candidates.sort(reverse=True)
    gold_to_predicted: dict[str, str] = {}
    predicted_to_gold: dict[str, str] = {}
    matched = []
    for score, gold_id, predicted_id in candidates:
        if gold_id in gold_to_predicted or predicted_id in predicted_to_gold:
            continue
        gold_to_predicted[gold_id] = predicted_id
        predicted_to_gold[predicted_id] = gold_id
        matched.append((gold_id, predicted_id, score))
    return gold_to_predicted, predicted_to_gold, matched


def edge_key(edge: dict[str, Any]) -> tuple[str, str, str]:
    return (str(edge.get("source")), canonical_relation(edge.get("relation")), str(edge.get("target")))


def score_edges(
    gold_edges: list[dict[str, Any]],
    predicted_edges: list[dict[str, Any]],
    gold_to_predicted: dict[str, str],
) -> tuple[dict[str, Any], dict[str, str]]:
    predicted_by_key = {edge_key(edge): edge for edge in predicted_edges}
    matched: dict[str, str] = {}
    for edge in gold_edges:
        source = gold_to_predicted.get(str(edge.get("source")))
        target = gold_to_predicted.get(str(edge.get("target")))
        if not source or not target:
            continue
        candidate = predicted_by_key.get((source, canonical_relation(edge.get("relation")), target))
        if candidate:
            matched[edge["id"]] = candidate["id"]
    return precision_recall_f1(len(matched), len(predicted_edges), len(gold_edges)), matched


def match_edges_fuzzy(
    gold_edges: list[dict[str, Any]],
    predicted_edges: list[dict[str, Any]],
    gold_nodes: dict[str, dict[str, Any]],
    predicted_nodes: dict[str, dict[str, Any]],
    threshold: float,
) -> dict[str, str]:
    """Match task edges without forcing repeated task concepts into one node."""
    matched: dict[str, str] = {}
    for gold_edge in gold_edges:
        gold_source = gold_nodes.get(gold_edge.get("source"))
        gold_target = gold_nodes.get(gold_edge.get("target"))
        if not gold_source or not gold_target:
            continue
        best: tuple[float, str] | None = None
        for predicted_edge in predicted_edges:
            if canonical_relation(predicted_edge.get("relation")) != canonical_relation(gold_edge.get("relation")):
                continue
            predicted_source = predicted_nodes.get(predicted_edge.get("source"))
            predicted_target = predicted_nodes.get(predicted_edge.get("target"))
            if not predicted_source or not predicted_target:
                continue
            score = min(node_similarity(gold_source, predicted_source), node_similarity(gold_target, predicted_target))
            if score >= threshold and (best is None or score > best[0]):
                best = (score, predicted_edge["id"])
        if best:
            matched[gold_edge["id"]] = best[1]
    return matched


def type_metrics(
    matches: list[tuple[str, str, float]],
    gold: dict[str, dict[str, Any]],
    predicted: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    known = 0
    correct = 0
    for gold_id, predicted_id, _ in matches:
        predicted_type = normalize_name(predicted[predicted_id].get("type"))
        if not predicted_type or predicted_type == "unknown":
            continue
        known += 1
        correct += predicted_type == normalize_name(gold[gold_id].get("type"))
    return {
        "matched_entities": len(matches),
        "typed_matches": known,
        "correct_types": correct,
        "type_coverage": known / len(matches) if matches else 0.0,
        "type_accuracy": correct / known if known else None,
    }


def evidence_binding_metrics(
    gold_nodes: dict[str, dict[str, Any]],
    gold_edges: dict[str, dict[str, Any]],
    predicted_nodes: dict[str, dict[str, Any]],
    predicted_edges: dict[str, dict[str, Any]],
    node_matches: dict[str, str],
    edge_matches: dict[str, str],
) -> dict[str, Any]:
    checks = []
    for gold_id, predicted_id in node_matches.items():
        required = set(gold_nodes[gold_id].get("evidence_ids", []))
        actual = set(predicted_nodes[predicted_id].get("evidence_ids", []))
        checks.append(bool(required & actual))
    for gold_id, predicted_id in edge_matches.items():
        required = set(gold_edges[gold_id].get("evidence_ids", []))
        actual = set(predicted_edges[predicted_id].get("evidence_ids", []))
        checks.append(bool(required & actual))
    return {"bound_items": sum(checks), "matched_items": len(checks), "accuracy": sum(checks) / len(checks) if checks else 0.0}


def tuple_equal(predicted: dict[str, Any], gold: dict[str, Any]) -> bool:
    left_value = safe_float(predicted.get("value"))
    right_value = safe_float(gold.get("value"))
    if left_value is None or right_value is None or abs(left_value - right_value) > 1e-9:
        return False
    left_operator = OPERATOR_ALIASES.get(str(predicted.get("operator", "")).upper(), str(predicted.get("operator", "")))
    right_operator = OPERATOR_ALIASES.get(str(gold.get("operator", "")).upper(), str(gold.get("operator", "")))
    if normalize_text(left_operator) != normalize_text(right_operator):
        return False
    if normalize_name(predicted.get("unit")) != normalize_name(gold.get("unit")):
        return False
    gold_condition = normalize_text(gold.get("condition", ""))
    predicted_condition = normalize_text(predicted.get("condition", ""))
    return not gold_condition or claim_similarity(gold_condition, predicted_condition) >= 0.35


def score_numeric_tuples(predicted_nodes: list[dict[str, Any]], gold_tuples: list[dict[str, Any]]) -> dict[str, Any]:
    predicted = [item for node in predicted_nodes for item in node.get("numeric_condition_tuples", [])]
    used: set[int] = set()
    matches = 0
    for gold in gold_tuples:
        for index, item in enumerate(predicted):
            if index not in used and tuple_equal(item, gold):
                used.add(index)
                matches += 1
                break
    return precision_recall_f1(matches, len(predicted), len(gold_tuples))


def score_aliases(predicted_nodes: list[dict[str, Any]], aliases: dict[str, list[str]]) -> dict[str, Any]:
    checks = []
    for canonical, variants in aliases.items():
        targets = {normalize_name(canonical), *(normalize_name(item) for item in variants)}
        matching_clusters = 0
        for node in predicted_nodes:
            node_names = {normalize_name(node.get("name", node.get("id", ""))), *(normalize_name(item) for item in node.get("aliases", []))}
            if targets & node_names:
                matching_clusters += 1
        checks.append(matching_clusters == 1)
    return {"correct": sum(checks), "gold_alias_groups": len(checks), "accuracy": sum(checks) / len(checks) if checks else 1.0}


def score_paths(
    questions: list[dict[str, Any]],
    gold_edges: dict[str, dict[str, Any]],
    matched_edges: dict[str, str],
) -> dict[str, Any]:
    rows = []
    for question in questions:
        path = question.get("gold_path", [])
        if not path:
            continue
        recovered = sum(edge_id in matched_edges for edge_id in path)
        rows.append(
            {
                "question_id": question["id"],
                "recovered_edges": recovered,
                "gold_edges": len(path),
                "edge_recall": recovered / len(path),
                "complete": recovered == len(path),
            }
        )
    return {
        "questions_with_paths": len(rows),
        "complete_paths": sum(row["complete"] for row in rows),
        "complete_path_recall": sum(row["complete"] for row in rows) / len(rows) if rows else 0.0,
        "mean_path_edge_recall": statistics.mean(row["edge_recall"] for row in rows) if rows else 0.0,
        "per_question": rows,
    }


def score_one(path: Path, threshold: float) -> dict[str, Any]:
    graph_records = load_jsonl(GRAPH_PATH)
    task_records = [item for item in graph_records if not item.get("properties", {}).get("audit_unit")]
    gold_node_list = list(canonical_nodes([item for item in task_records if item.get("kind") == "node"]).values())
    gold_edge_list_raw = [item for item in task_records if item.get("kind") == "edge"]
    # Deduplicate task edges using canonical endpoint labels, while retaining one source id.
    all_gold_nodes_by_id = index_by_id((item for item in graph_records if item.get("kind") == "node"), "gold node")
    edge_dedup: dict[tuple[str, str, str], dict[str, Any]] = {}
    for edge in gold_edge_list_raw:
        key = (
            normalize_name(all_gold_nodes_by_id[edge["source"]]["name"]),
            canonical_relation(edge["relation"]),
            normalize_name(all_gold_nodes_by_id[edge["target"]]["name"]),
        )
        edge_dedup.setdefault(key, edge)
    gold_edge_list = list(edge_dedup.values())

    predicted_records = load_jsonl(path)
    predicted_nodes_list = [item for item in predicted_records if item.get("kind") == "node"]
    predicted_edges_list = [item for item in predicted_records if item.get("kind") == "edge"]
    predicted_nodes = index_by_id(predicted_nodes_list, "predicted node")
    predicted_edges = index_by_id(predicted_edges_list, "predicted edge")
    gold_nodes = index_by_id(gold_node_list, "canonical gold node")
    gold_edges = index_by_id(gold_edge_list, "canonical gold edge")

    gold_to_predicted, predicted_to_gold, matches = match_nodes(gold_node_list, predicted_nodes_list, threshold)
    canonical_prediction = {
        f"{normalize_name(gold_nodes[gold_id].get('type'))}::{normalize_name(gold_nodes[gold_id].get('name'))}": predicted_id
        for gold_id, predicted_id in gold_to_predicted.items()
    }
    all_gold_to_predicted = {
        node_id: canonical_prediction[key]
        for node_id, node in all_gold_nodes_by_id.items()
        for key in [f"{normalize_name(node.get('type'))}::{normalize_name(node.get('name'))}"]
        if key in canonical_prediction
    }
    entity_scores = precision_recall_f1(len(matches), len(predicted_nodes_list), len(gold_node_list))
    relation_scores, matched_edges = score_edges(gold_edge_list, predicted_edges_list, all_gold_to_predicted)
    matched_raw_edges = match_edges_fuzzy(
        gold_edge_list_raw, predicted_edges_list, all_gold_nodes_by_id, predicted_nodes, threshold
    )
    paths = score_paths(load_jsonl(QUESTIONS_PATH), index_by_id(gold_edge_list_raw, "task edge"), matched_raw_edges)

    audit_rows = []
    for unit in load_jsonl(AUDIT_PATH):
        evidence_id = unit["evidence_id"]
        unit_gold_nodes = [all_gold_nodes_by_id[item] for item in unit["gold_nodes"]]
        all_gold_edges_by_id = index_by_id((item for item in graph_records if item.get("kind") == "edge"), "gold edge")
        unit_gold_edges = [all_gold_edges_by_id[item] for item in unit["gold_edges"]]
        explicit_unit_nodes = [
            item for item in predicted_nodes_list
            if item.get("properties", {}).get("audit_unit") == unit["id"]
        ]
        scoped_nodes = explicit_unit_nodes or [
            item for item in predicted_nodes_list if evidence_id in item.get("evidence_ids", [])
        ]
        scope_method = "explicit_audit_unit" if explicit_unit_nodes else "evidence_id"
        if not scoped_nodes:
            # Fail closed: never score against the entire predicted graph.
            scope_method = "no_evidence_binding"
            unit_entity = precision_recall_f1(0, 0, len(unit_gold_nodes))
            unit_relation = precision_recall_f1(0, 0, len(unit_gold_edges))
            audit_rows.append(
                {
                    "unit_id": unit["id"],
                    "kind": unit["kind"],
                    "scope_method": scope_method,
                    "entity": unit_entity,
                    "relation": unit_relation,
                    "type": {
                        "matched_entities": 0,
                        "typed_matches": 0,
                        "correct_types": 0,
                        "type_coverage": 0.0,
                        "type_accuracy": None,
                    },
                    "evidence_binding": {
                        "bound_nodes": 0,
                        "bound_edges": 0,
                        "node_binding_rate": 0.0,
                        "edge_binding_rate": 0.0,
                    },
                    "numeric_condition_tuples": {"correct": 0, "gold": 0, "accuracy": 1.0},
                    "alias_normalization": {"correct": 0, "gold": 0, "accuracy": 1.0},
                    "unsupported_node_ratio": 0.0,
                    "unsupported_edge_ratio": 0.0,
                    "diagnostic": "no_scoped_prediction_for_audit_unit",
                }
            )
            continue
        scoped_node_ids = {item["id"] for item in scoped_nodes}
        explicit_unit_edges = [
            item for item in predicted_edges_list
            if item.get("properties", {}).get("audit_unit") == unit["id"]
        ]
        scoped_edges = explicit_unit_edges or [
            item for item in predicted_edges_list
            if evidence_id in item.get("evidence_ids", [])
            or (item.get("source") in scoped_node_ids and item.get("target") in scoped_node_ids)
        ]
        unit_g2p, unit_p2g, unit_matches = match_nodes(unit_gold_nodes, scoped_nodes, threshold)
        unit_entity = precision_recall_f1(len(unit_matches), len(scoped_nodes), len(unit_gold_nodes))
        unit_relation, unit_edge_matches = score_edges(unit_gold_edges, scoped_edges, unit_g2p)
        unit_predicted_nodes = index_by_id(scoped_nodes, "scoped node") if scoped_nodes else {}
        unit_predicted_edges = index_by_id(scoped_edges, "scoped edge") if scoped_edges else {}
        audit_rows.append(
            {
                "unit_id": unit["id"], "kind": unit["kind"], "scope_method": scope_method,
                "entity": unit_entity, "relation": unit_relation,
                "type": type_metrics(unit_matches, index_by_id(unit_gold_nodes, "unit gold node"), unit_predicted_nodes),
                "evidence_binding": evidence_binding_metrics(
                    index_by_id(unit_gold_nodes, "unit gold node"), index_by_id(unit_gold_edges, "unit gold edge"),
                    unit_predicted_nodes, unit_predicted_edges, unit_g2p, unit_edge_matches,
                ),
                "numeric_condition_tuples": score_numeric_tuples(scoped_nodes, unit.get("gold_numeric_condition_tuples", [])),
                "alias_normalization": score_aliases(scoped_nodes, unit.get("gold_aliases", {})),
                "unsupported_node_ratio": (len(scoped_nodes) - len(unit_p2g)) / len(scoped_nodes) if scoped_nodes else 0.0,
                "unsupported_edge_ratio": (len(scoped_edges) - len(unit_edge_matches)) / len(scoped_edges) if scoped_edges else 0.0,
            }
        )

    audit_typed_matches = sum(row["type"]["typed_matches"] for row in audit_rows)
    audit_matched_entities = sum(row["type"]["matched_entities"] for row in audit_rows)
    audit_correct_types = sum(row["type"]["correct_types"] for row in audit_rows)
    known_schema_records = [item for item in predicted_records if item.get("schema_valid") is not None]
    isolated = set(predicted_nodes) - {
        endpoint for edge in predicted_edges_list for endpoint in (edge.get("source"), edge.get("target"))
    }
    return {
        "predicted_path": str(path),
        "matching_threshold": threshold,
        "task_graph": {
            "entity": entity_scores,
            "relation_direction_sensitive": relation_scores,
            "type": type_metrics(matches, gold_nodes, predicted_nodes),
            "evidence_binding": evidence_binding_metrics(gold_nodes, gold_edges, predicted_nodes, predicted_edges, gold_to_predicted, matched_edges),
            "gold_path": paths,
            "precision_caveat": "Task gold graph only covers benchmark needs; unmatched extracted records are not automatically hallucinations. Use audit-unit precision as the primary precision estimate.",
        },
        "audit_units": audit_rows,
        "audit_macro": {
            "entity_f1": statistics.mean(row["entity"]["f1"] for row in audit_rows),
            "relation_f1": statistics.mean(row["relation"]["f1"] for row in audit_rows),
            "type_accuracy": audit_correct_types / audit_typed_matches if audit_typed_matches else None,
            "type_coverage": audit_typed_matches / audit_matched_entities if audit_matched_entities else 0.0,
            "numeric_tuple_exact_match_f1": statistics.mean(row["numeric_condition_tuples"]["f1"] for row in audit_rows),
            "evidence_binding_accuracy": statistics.mean(row["evidence_binding"]["accuracy"] for row in audit_rows),
            "alias_normalization_accuracy": statistics.mean(row["alias_normalization"]["accuracy"] for row in audit_rows),
            "unsupported_node_ratio": statistics.mean(row["unsupported_node_ratio"] for row in audit_rows),
            "unsupported_edge_ratio": statistics.mean(row["unsupported_edge_ratio"] for row in audit_rows),
        },
        "diagnostics": {
            "nodes": len(predicted_nodes), "edges": len(predicted_edges), "isolated_nodes": len(isolated),
            "schema_valid_rate": (
                sum(bool(item.get("schema_valid")) for item in known_schema_records) / len(known_schema_records)
                if known_schema_records else None
            ),
            "schema_valid_coverage": len(known_schema_records) / len(predicted_records) if predicted_records else 0.0,
        },
    }


def canonical_sets(path: Path) -> tuple[set[str], set[str]]:
    records = load_jsonl(path)
    nodes = {normalize_name(item.get("name", item.get("id"))) for item in records if item.get("kind") == "node"}
    edges = {
        f"{normalize_name(item.get('source'))}|{canonical_relation(item.get('relation'))}|{normalize_name(item.get('target'))}"
        for item in records if item.get("kind") == "edge"
    }
    return nodes, edges


def jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / len(left | right) if left or right else 1.0


def stability(paths: list[Path], reports: list[dict[str, Any]]) -> dict[str, Any]:
    if len(paths) < 2:
        return {"run_count": len(paths), "available": False, "reason": "Provide at least two independent graph exports."}
    sets = [canonical_sets(path) for path in paths]
    pairs = list(itertools.combinations(range(len(paths)), 2))
    return {
        "run_count": len(paths), "available": True,
        "mean_entity_jaccard": statistics.mean(jaccard(sets[a][0], sets[b][0]) for a, b in pairs),
        "mean_edge_jaccard": statistics.mean(jaccard(sets[a][1], sets[b][1]) for a, b in pairs),
        "audit_entity_f1_stddev": statistics.pstdev(report["audit_macro"]["entity_f1"] for report in reports),
        "audit_relation_f1_stddev": statistics.pstdev(report["audit_macro"]["relation_f1"] for report in reports),
    }


def build_efficiency(metadata_paths: list[Path], run_count: int) -> dict[str, Any]:
    if not metadata_paths:
        return {
            "available": False,
            "reason": "Provide one --run-metadata JSON per predicted graph with elapsed_seconds and cost_usd.",
        }
    if len(metadata_paths) != run_count:
        raise RuntimeError("--run-metadata count must equal --predicted count")
    rows = [json.loads(path.read_text(encoding="utf-8")) for path in metadata_paths]
    elapsed = [float(item["elapsed_seconds"]) for item in rows if item.get("elapsed_seconds") is not None]
    costs = [float(item["cost_usd"]) for item in rows if item.get("cost_usd") is not None]
    return {
        "available": True,
        "runs": rows,
        "mean_elapsed_seconds": statistics.mean(elapsed) if elapsed else None,
        "elapsed_seconds_stddev": statistics.pstdev(elapsed) if len(elapsed) > 1 else (0.0 if elapsed else None),
        "mean_cost_usd": statistics.mean(costs) if costs else None,
        "total_cost_usd": sum(costs) if costs else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predicted", type=Path, action="append", required=True, help="repeat for independent graph builds")
    parser.add_argument(
        "--run-metadata", type=Path, action="append", default=[],
        help="repeat once per graph; JSON may contain run_id, elapsed_seconds, cost_usd, and token counts",
    )
    parser.add_argument("--name-threshold", type=float, default=0.72)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reports = [score_one(path, args.name_threshold) for path in args.predicted]
    payload = {
        "runs": reports,
        "stability": stability(args.predicted, reports),
        "build_efficiency": build_efficiency(args.run_metadata, len(reports)),
    }
    write_json(args.output, payload)
    for report in reports:
        print(
            f"kg score {Path(report['predicted_path']).name}: "
            f"audit_entity_f1={report['audit_macro']['entity_f1']:.3f} "
            f"audit_relation_f1={report['audit_macro']['relation_f1']:.3f} "
            f"path_complete={report['task_graph']['gold_path']['complete_path_recall']:.3f}"
        )
    print(f"report={args.output}")


if __name__ == "__main__":
    main()
