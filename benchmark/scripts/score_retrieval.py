#!/usr/bin/env python3
"""Score evidence retrieval results produced by run_graphrag_benchmark.py."""

from __future__ import annotations

import argparse
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from benchmark_common import (
    GRAPH_PATH,
    QUESTIONS_PATH,
    claim_similarity,
    index_by_id,
    load_jsonl,
    normalize_name,
    precision_recall_f1,
    validate_result_records,
    write_json,
)

RELATION_ALIASES = {"USES_SIGNAL": "HAS_SIGNAL", "REQUIRES_SIGNAL": "HAS_SIGNAL"}


def ndcg_at_10(ranked: list[str], relevant: set[str]) -> float:
    gains = [1.0 if item in relevant else 0.0 for item in ranked[:10]]
    dcg = sum(gain / math.log2(index + 2) for index, gain in enumerate(gains))
    ideal = sum(1.0 / math.log2(index + 2) for index in range(min(10, len(relevant))))
    return dcg / ideal if ideal else 1.0


def bootstrap_mean(values: list[float], samples: int, seed: int) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "ci95_low": None, "ci95_high": None}
    rng = random.Random(seed)
    estimates = []
    for _ in range(samples):
        draw = [values[rng.randrange(len(values))] for _ in values]
        estimates.append(statistics.mean(draw))
    estimates.sort()
    return {
        "mean": statistics.mean(values),
        "ci95_low": estimates[int(0.025 * (len(estimates) - 1))],
        "ci95_high": estimates[int(0.975 * (len(estimates) - 1))],
    }


def optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def canonical_relation(value: Any) -> str:
    relation = str(value or "").strip().upper()
    return RELATION_ALIASES.get(relation, relation)


def _endpoint_matches(actual: Any, gold_node: dict[str, Any]) -> bool:
    actual_name = normalize_name(actual)
    candidates = [
        gold_node.get("name", ""),
        gold_node.get("id", ""),
        *gold_node.get("aliases", []),
    ]
    for candidate in candidates:
        gold_name = normalize_name(candidate)
        if not actual_name or not gold_name:
            continue
        if actual_name == gold_name:
            return True
        if len(actual_name) >= 4 and (
            actual_name in gold_name or gold_name in actual_name
        ):
            return True
        if claim_similarity(actual, candidate) >= 0.82:
            return True
    return False


def retrieved_graph_edges(result: dict[str, Any]) -> list[dict[str, str]]:
    edges = list(result.get("retrieved_graph_edges") or [])
    if not isinstance(edges, list):
        edges = []
    for item in result.get("retrieved_items", []) or []:
        if isinstance(item, dict) and isinstance(item.get("graph_edge"), dict):
            edges.append(item["graph_edge"])
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source") or edge.get("src_id") or "").strip()
        target = str(edge.get("target") or edge.get("tgt_id") or "").strip()
        relation = canonical_relation(
            edge.get("relation")
            or edge.get("relation_type")
            or edge.get("keywords")
        )
        key = (source, relation, target)
        if not source or not target or not relation or key in seen:
            continue
        seen.add(key)
        normalized.append(
            {"source": source, "relation": relation, "target": target}
        )
    return normalized


def true_graph_path_score(
    question: dict[str, Any],
    result: dict[str, Any],
    edges: dict[str, dict[str, Any]],
    nodes: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    path = question.get("gold_kg_path", [])
    if not path:
        return {
            "evaluable": False,
            "gold_edges": 0,
            "matched_edges": 0,
            "edge_recall": None,
            "complete": None,
            "connected": None,
        }
    predicted = retrieved_graph_edges(result)
    used: set[int] = set()
    matched: list[tuple[int, dict[str, str]]] = []
    for edge_id in path:
        gold = edges[edge_id]
        gold_source = nodes[gold["source"]]
        gold_target = nodes[gold["target"]]
        for index, candidate in enumerate(predicted):
            if index in used:
                continue
            if canonical_relation(candidate["relation"]) != canonical_relation(
                gold["relation"]
            ):
                continue
            if not _endpoint_matches(candidate["source"], gold_source):
                continue
            if not _endpoint_matches(candidate["target"], gold_target):
                continue
            used.add(index)
            matched.append((index, candidate))
            break
    # Connectivity is a property of the matched gold-node identities, not the
    # literal predicted labels.  The same entity may be rendered with two
    # different valid aliases on adjacent retrieved edges (for example
    # ``AEB`` and ``自动紧急制动系统``).
    connected = len(matched) == len(path) and all(
        edges[left_id]["target"] == edges[right_id]["source"]
        for left_id, right_id in zip(path, path[1:])
    )
    recovered = len(matched)
    return {
        "evaluable": True,
        "gold_edges": len(path),
        "matched_edges": recovered,
        "edge_recall": recovered / len(path),
        "complete": recovered == len(path) and connected,
        "connected": connected,
    }


def row_score(
    result: dict[str, Any],
    question: dict[str, Any],
    edges: dict[str, dict[str, Any]],
    nodes: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    gold = set(question.get("gold_evidence_ids", []))
    ranked = list(dict.fromkeys(result.get("ranked_evidence_ids", result.get("retrieved_evidence_ids", []))))
    retrieved = set(ranked)
    overlap = gold & retrieved
    evidence = precision_recall_f1(len(overlap), len(retrieved), len(gold))
    reasoning_path = question.get("gold_reasoning_path", question.get("gold_path", []))
    recovered_evidence_edges = 0
    for edge_id in reasoning_path:
        edge_evidence = set(edges[edge_id].get("evidence_ids", []))
        recovered_evidence_edges += bool(edge_evidence & retrieved)
    evidence_path_recall = (
        recovered_evidence_edges / len(reasoning_path)
        if reasoning_path
        else None
    )
    evidence_path_complete = (
        recovered_evidence_edges == len(reasoning_path)
        if reasoning_path
        else None
    )
    graph_path = true_graph_path_score(question, result, edges, nodes or {})
    legacy_contract = "gold_kg_path" not in question
    items = result.get("retrieved_items", [])
    total_tokens = sum(int(item.get("token_estimate", 0)) for item in items)
    # A retrieved item may map to several benchmark evidence records. Allocate
    # its tokens fractionally so one broad chunk cannot count as 100% useful
    # merely because it contains a single gold clause among many clauses.
    relevant_tokens = sum(
        int(item.get("token_estimate", 0))
        * len(set(item.get("evidence_ids", [])) & gold)
        / len(set(item.get("evidence_ids", [])))
        for item in items
        if item.get("evidence_ids")
    )
    return {
        "question_id": question["id"],
        "mode": result["mode"],
        "task_type": question["task_type"],
        "answerable": question["answerable"],
        "evidence": evidence,
        "ndcg_at_10": ndcg_at_10(ranked, gold),
        "gold_path_edge_recall": (
            evidence_path_recall
            if legacy_contract
            else graph_path["edge_recall"]
        ),
        "gold_path_complete": (
            evidence_path_complete
            if legacy_contract
            else graph_path["complete"]
        ),
        "gold_path_graph": graph_path,
        "gold_path_evidence_support_edge_recall": evidence_path_recall,
        "gold_path_evidence_support_complete": evidence_path_complete,
        "context_tokens": total_tokens or int(result.get("context_tokens", 0)),
        "effective_evidence_tokens": relevant_tokens,
        "effective_evidence_per_1000_tokens": (1000 * relevant_tokens / total_tokens) if total_tokens else 0.0,
        "irrelevant_evidence_ratio": (len(retrieved - gold) / len(retrieved)) if retrieved else 0.0,
        "untraceable_item_ratio": (
            sum(not item.get("evidence_ids") for item in items) / len(items)
            if items else 0.0
        ),
        "latency_seconds": float(result.get("retrieval_latency_seconds", 0.0)),
        "estimated_cost_usd": optional_float(result.get("retrieval_cost_usd")),
        "missing_evidence_ids": sorted(gold - retrieved),
        "extra_evidence_ids": sorted(retrieved - gold),
    }


def summarize(rows: list[dict[str, Any]], samples: int, seed: int) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["mode"], "__all__")].append(row)
        groups[(row["mode"], row["task_type"])].append(row)
    summaries = []
    metrics = {
        "evidence_precision": lambda row: row["evidence"]["precision"],
        "evidence_recall": lambda row: row["evidence"]["recall"],
        "evidence_f1": lambda row: row["evidence"]["f1"],
        "ndcg_at_10": lambda row: row["ndcg_at_10"],
        "gold_path_complete": lambda row: (
            None
            if row["gold_path_complete"] is None
            else float(row["gold_path_complete"])
        ),
        "gold_path_edge_recall": lambda row: row["gold_path_edge_recall"],
        "gold_path_evidence_support_complete": lambda row: (
            None
            if row["gold_path_evidence_support_complete"] is None
            else float(row["gold_path_evidence_support_complete"])
        ),
        "gold_path_evidence_support_edge_recall": lambda row: row[
            "gold_path_evidence_support_edge_recall"
        ],
        "effective_evidence_per_1000_tokens": lambda row: row["effective_evidence_per_1000_tokens"],
        "irrelevant_evidence_ratio": lambda row: row["irrelevant_evidence_ratio"],
        "untraceable_item_ratio": lambda row: row["untraceable_item_ratio"],
        "latency_seconds": lambda row: row["latency_seconds"],
        "estimated_cost_usd": lambda row: row["estimated_cost_usd"],
    }
    for (mode, task_type), group in sorted(groups.items()):
        summaries.append(
            {
                "mode": mode,
                "task_type": task_type,
                "question_count": len(group),
                "metrics": {
                    name: bootstrap_mean(
                        [value for row in group for value in [getter(row)] if value is not None],
                        samples,
                        seed + index,
                    )
                    for index, (name, getter) in enumerate(metrics.items())
                },
            }
        )
    return {"summaries": summaries}


def paired_comparisons(
    rows: list[dict[str, Any]],
    *,
    baseline_mode: str,
    samples: int,
    seed: int,
) -> list[dict[str, Any]]:
    by_key = {(row["question_id"], row["mode"]): row for row in rows}
    modes = sorted({row["mode"] for row in rows} - {baseline_mode})
    task_types = ["__all__", *sorted({row["task_type"] for row in rows})]
    getters = {
        "evidence_recall": lambda row: row["evidence"]["recall"],
        "evidence_f1": lambda row: row["evidence"]["f1"],
        "gold_path_complete": lambda row: (
            None
            if row["gold_path_complete"] is None
            else float(row["gold_path_complete"])
        ),
    }
    output = []
    for task_index, task_type in enumerate(task_types):
        question_ids = {
            row["question_id"]
            for row in rows
            if task_type == "__all__" or row["task_type"] == task_type
        }
        for mode_index, mode in enumerate(modes):
            paired_ids = sorted(
                question_id
                for question_id in question_ids
                if (question_id, baseline_mode) in by_key
                and (question_id, mode) in by_key
            )
            if not paired_ids:
                continue
            metrics = {}
            for metric_index, (name, getter) in enumerate(getters.items()):
                deltas = []
                for question_id in paired_ids:
                    left = getter(by_key[(question_id, mode)])
                    right = getter(by_key[(question_id, baseline_mode)])
                    if left is not None and right is not None:
                        deltas.append(float(left) - float(right))
                metrics[name] = bootstrap_mean(
                    deltas,
                    samples,
                    seed + task_index * 1009 + mode_index * 101 + metric_index,
                )
            output.append(
                {
                    "baseline_mode": baseline_mode,
                    "mode": mode,
                    "task_type": task_type,
                    "paired_question_count": len(paired_ids),
                    "metrics_delta": metrics,
                }
            )
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=39901)
    parser.add_argument("--paired-baseline", default="naive")
    args = parser.parse_args()
    questions = index_by_id(load_jsonl(QUESTIONS_PATH), "question")
    graph = load_jsonl(GRAPH_PATH)
    edges = index_by_id(
        (item for item in graph if item.get("kind") == "edge"),
        "edge",
    )
    nodes = index_by_id(
        (item for item in graph if item.get("kind") == "node"),
        "node",
    )
    results = load_jsonl(args.results)
    validate_result_records(results)
    rows = []
    for result in results:
        question_id = result.get("question_id")
        if question_id not in questions:
            raise RuntimeError(f"Unknown question_id in results: {question_id}")
        rows.append(row_score(result, questions[question_id], edges, nodes))
    payload = {
        "run_manifest": results[0]["run_manifest"] if results else None,
        "scoring_config": {
            "bootstrap_samples": args.bootstrap_samples,
            "seed": args.seed,
            "paired_baseline": args.paired_baseline,
        },
        "per_question": rows,
        **summarize(rows, args.bootstrap_samples, args.seed),
        "paired_comparisons": paired_comparisons(
            rows,
            baseline_mode=args.paired_baseline,
            samples=args.bootstrap_samples,
            seed=args.seed,
        ),
    }
    write_json(args.output, payload)
    print(f"retrieval score rows={len(rows)} report={args.output}")


if __name__ == "__main__":
    main()
