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

from benchmark_common import GRAPH_PATH, QUESTIONS_PATH, index_by_id, load_jsonl, precision_recall_f1, write_json


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


def row_score(
    result: dict[str, Any],
    question: dict[str, Any],
    edges: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    gold = set(question.get("gold_evidence_ids", []))
    ranked = list(dict.fromkeys(result.get("ranked_evidence_ids", result.get("retrieved_evidence_ids", []))))
    retrieved = set(ranked)
    overlap = gold & retrieved
    evidence = precision_recall_f1(len(overlap), len(retrieved), len(gold))
    path = question.get("gold_path", [])
    recovered_edges = 0
    for edge_id in path:
        edge_evidence = set(edges[edge_id].get("evidence_ids", []))
        recovered_edges += bool(edge_evidence & retrieved)
    path_edge_recall = recovered_edges / len(path) if path else 1.0
    path_complete = recovered_edges == len(path)
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
        "gold_path_edge_recall": path_edge_recall,
        "gold_path_complete": path_complete,
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
        "gold_path_complete": lambda row: float(row["gold_path_complete"]),
        "gold_path_edge_recall": lambda row: row["gold_path_edge_recall"],
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=39901)
    args = parser.parse_args()
    questions = index_by_id(load_jsonl(QUESTIONS_PATH), "question")
    edges = index_by_id((item for item in load_jsonl(GRAPH_PATH) if item.get("kind") == "edge"), "edge")
    rows = []
    for result in load_jsonl(args.results):
        question_id = result.get("question_id")
        if question_id not in questions:
            raise RuntimeError(f"Unknown question_id in results: {question_id}")
        rows.append(row_score(result, questions[question_id], edges))
    payload = {"per_question": rows, **summarize(rows, args.bootstrap_samples, args.seed)}
    write_json(args.output, payload)
    print(f"retrieval score rows={len(rows)} report={args.output}")


if __name__ == "__main__":
    main()
