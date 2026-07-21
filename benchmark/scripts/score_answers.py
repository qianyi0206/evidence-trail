#!/usr/bin/env python3
"""Score structured answers, atomic claims, citations, and refusal behavior."""

from __future__ import annotations

import argparse
import random
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from benchmark_common import (
    QUESTIONS_PATH,
    claim_similarity,
    index_by_id,
    load_jsonl,
    normalize_text,
    parse_json_object,
    precision_recall_f1,
    recursive_normalized_equal,
    safe_float,
    set_scores,
    write_json,
)

_BAG_REF_RE = re.compile(r"^[EeRr](\d+)$")


def flatten(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        return [item for key, child in value.items() for item in flatten(child, f"{prefix}.{key}" if prefix else key)]
    if isinstance(value, list):
        return [item for index, child in enumerate(value) for item in flatten(child, f"{prefix}[{index}]")]
    return [(prefix, value)]


def field_accuracy(predicted: Any, gold: Any) -> dict[str, Any]:
    predicted_fields = dict(flatten(predicted))
    gold_fields = dict(flatten(gold))
    correct = sum(
        path in predicted_fields and recursive_normalized_equal(predicted_fields[path], value)
        for path, value in gold_fields.items()
    )
    return {"correct": correct, "gold_fields": len(gold_fields), "accuracy": correct / len(gold_fields) if gold_fields else 1.0}


def numeric_date_accuracy(predicted: Any, gold: Any) -> dict[str, Any]:
    predicted_fields = dict(flatten(predicted))
    selected = []
    for path, value in flatten(gold):
        numeric = safe_float(value) is not None and not isinstance(value, bool)
        date_like = any(token in path.lower() for token in ("date", "time", "month", "year", "日期", "时间"))
        if numeric or date_like:
            selected.append((path, value))
    correct = sum(path in predicted_fields and recursive_normalized_equal(predicted_fields[path], value) for path, value in selected)
    return {"correct": correct, "gold_fields": len(selected), "accuracy": correct / len(selected) if selected else 1.0}


def claim_scores(predicted_claims: list[str], gold_claims: list[str], threshold: float) -> dict[str, Any]:
    candidates = []
    for predicted_index, predicted in enumerate(predicted_claims):
        for gold_index, gold in enumerate(gold_claims):
            similarity = claim_similarity(predicted, gold)
            if similarity >= threshold:
                candidates.append((similarity, predicted_index, gold_index))
    candidates.sort(reverse=True)
    used_predicted: set[int] = set()
    used_gold: set[int] = set()
    pairs = []
    for similarity, predicted_index, gold_index in candidates:
        if predicted_index in used_predicted or gold_index in used_gold:
            continue
        used_predicted.add(predicted_index)
        used_gold.add(gold_index)
        pairs.append({"predicted_index": predicted_index, "gold_index": gold_index, "similarity": similarity})
    scores = precision_recall_f1(len(pairs), len(predicted_claims), len(gold_claims))
    scores["matches"] = pairs
    return scores


def citations_from(prediction: dict[str, Any], result: dict[str, Any]) -> list[str]:
    citations = prediction.get("citations", result.get("citations", []))
    return [str(item) for item in citations] if isinstance(citations, list) else []


def _retrieved_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    items = result.get("retrieved_items") or []
    return [item for item in items if isinstance(item, dict)]


def expand_citation_ids(citations: list[str], result: dict[str, Any]) -> set[str]:
    """Map bag refs (E1/R1) and raw ids onto gold evidence ids when possible."""
    items = _retrieved_items(result)
    ref_map = result.get("reference_map") or {}
    if not isinstance(ref_map, dict):
        ref_map = {}
    expanded: set[str] = set()
    for raw in citations:
        citation = str(raw).strip()
        if not citation:
            continue
        mapped = ref_map.get(citation)
        if isinstance(mapped, list):
            expanded.update(str(item) for item in mapped)
            continue
        if isinstance(mapped, str) and mapped:
            expanded.add(mapped)
            continue
        match = _BAG_REF_RE.fullmatch(citation)
        if match and items:
            index = int(match.group(1)) - 1
            if 0 <= index < len(items):
                ids = items[index].get("evidence_ids") or []
                if isinstance(ids, list) and ids:
                    expanded.update(str(item) for item in ids)
                    continue
        expanded.add(citation)
    return expanded


def context_blob_from_result(result: dict[str, Any]) -> str:
    texts = [
        str(item.get("text") or "")
        for item in _retrieved_items(result)
        if item.get("text")
    ]
    if texts:
        return "\n".join(texts)
    # Fallback fields some runners may emit.
    for key in ("context_text", "evidence_text", "bag_text"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def claim_supported_by_context(claim: str, context_blob: str) -> bool:
    """Faithfulness vs retrieved text only — independent of gold claim matching."""
    claim = (claim or "").strip()
    if not claim or not context_blob.strip():
        return False
    claim_norm = normalize_text(claim)
    context_norm = normalize_text(context_blob)
    if len(claim_norm) >= 6 and claim_norm in context_norm:
        return True
    claim_numbers = re.findall(r"\d+(?:\.\d+)?", claim)
    if claim_numbers:
        context_numbers = set(re.findall(r"\d+(?:\.\d+)?", context_blob))
        if all(number in context_numbers for number in claim_numbers):
            return True
    # Character bigram overlap against the full bag (short regulatory claims).
    return claim_similarity(claim, context_blob) >= 0.35


def extract_set_items(answer: Any) -> list[Any]:
    """Normalize common answer shapes for set_f1 scoring."""
    if isinstance(answer, list):
        return answer
    if not isinstance(answer, dict):
        return []
    for key in (
        "items",
        "scenarios",
        "values",
        "list",
        "categories",
        "entries",
        "results",
    ):
        value = answer.get(key)
        if isinstance(value, list):
            return value
    return []


def score_row(result: dict[str, Any], question: dict[str, Any], claim_threshold: float) -> dict[str, Any]:
    prediction = parse_json_object(result.get("prediction", result.get("answer", {})))
    answer = prediction.get("answer", prediction)
    predicted_claims = prediction.get("claims", result.get("claims", []))
    if not isinstance(predicted_claims, list):
        predicted_claims = []
    predicted_claims = [str(item) for item in predicted_claims]
    gold_claims = [item["text"] for item in question.get("atomic_claims", [])]
    atomic = claim_scores(predicted_claims, gold_claims, claim_threshold)
    citations = citations_from(prediction, result)
    citation_set = expand_citation_ids(citations, result)
    gold_evidence = set(question.get("gold_evidence_ids", []))
    citation_metric = precision_recall_f1(
        len(citation_set & gold_evidence), len(citation_set), len(gold_evidence)
    )
    retrieved = set(str(item) for item in (result.get("retrieved_evidence_ids") or []))
    context_blob = context_blob_from_result(result)
    if not predicted_claims:
        # Empty claims are not faithful evidence of grounding (including refusals).
        faithfulness = 0.0
    elif context_blob.strip():
        grounded = sum(
            1 for claim in predicted_claims if claim_supported_by_context(claim, context_blob)
        )
        faithfulness = grounded / len(predicted_claims)
    else:
        # No retrieved text available: fall back to citation ∩ retrieved ids only.
        if not retrieved:
            faithfulness = 0.0
        else:
            claim_citations = prediction.get("claim_citations", {})
            grounded = 0
            for index, _ in enumerate(predicted_claims):
                if isinstance(claim_citations, dict):
                    local = claim_citations.get(str(index), claim_citations.get(index, citations))
                else:
                    local = citations
                local_set = expand_citation_ids(
                    [str(item) for item in local] if isinstance(local, list) else citations,
                    result,
                )
                grounded += bool(local_set & retrieved)
            faithfulness = grounded / len(predicted_claims)

    method = question["scoring_method"]
    if method == "structured_exact_match":
        primary = float(recursive_normalized_equal(answer, question["gold_answer"]))
        detail: dict[str, Any] = {"exact_match": bool(primary)}
    elif method == "set_f1":
        predicted_items = extract_set_items(answer)
        gold_answer = question.get("gold_answer") or {}
        gold_items = (
            gold_answer.get("items", [])
            if isinstance(gold_answer, dict)
            else (gold_answer if isinstance(gold_answer, list) else [])
        )
        detail = set_scores(predicted_items, gold_items)
        primary = detail["f1"]
    elif method == "claim_f1":
        detail = atomic
        primary = atomic["f1"]
    elif method == "unanswerable":
        answer_object = answer if isinstance(answer, dict) else {}
        predicted_unanswerable = prediction.get("answerable") is False or answer_object.get("answerable") is False
        primary = float(predicted_unanswerable)
        detail = {
            "correct_refusal": bool(predicted_unanswerable),
            "reason": prediction.get("reason", answer_object.get("reason", "")),
        }
    else:
        raise RuntimeError(f"Unsupported method: {method}")

    return {
        "question_id": question["id"], "mode": result["mode"], "task_type": question["task_type"],
        "answerable": question["answerable"], "scoring_method": method,
        "primary_score": primary, "method_detail": detail,
        "structured_exact_match": float(recursive_normalized_equal(answer, question["gold_answer"])) if question["answerable"] else None,
        "multi_field": field_accuracy(answer, question["gold_answer"]),
        "numeric_date": numeric_date_accuracy(answer, question["gold_answer"]),
        "atomic_claims": atomic,
        "citation_correctness": citation_metric["precision"],
        "citation_completeness": citation_metric["recall"],
        "faithfulness_to_retrieved_context": faithfulness,
        "unanswerable_correct": (primary if not question["answerable"] else None),
        "answer_latency_seconds": float(result.get("answer_latency_seconds", 0.0)),
        "estimated_cost_usd": (
            float(result["answer_cost_usd"])
            if result.get("answer_cost_usd") not in {None, ""}
            else None
        ),
        "prediction": prediction,
    }


def bootstrap(values: list[float], samples: int, rng: random.Random) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "ci95_low": None, "ci95_high": None}
    estimates = sorted(
        statistics.mean(values[rng.randrange(len(values))] for _ in values)
        for _ in range(samples)
    )
    return {
        "mean": statistics.mean(values),
        "ci95_low": estimates[int(0.025 * (len(estimates) - 1))],
        "ci95_high": estimates[int(0.975 * (len(estimates) - 1))],
    }


def summaries(rows: list[dict[str, Any]], samples: int, seed: int) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["mode"], "__all__")].append(row)
        groups[(row["mode"], row["task_type"])].append(row)
    getters = {
        "primary_score": lambda row: row["primary_score"],
        "multi_field_accuracy": lambda row: row["multi_field"]["accuracy"],
        "numeric_date_exact_match": lambda row: row["numeric_date"]["accuracy"],
        "atomic_claim_precision": lambda row: row["atomic_claims"]["precision"],
        "atomic_claim_recall": lambda row: row["atomic_claims"]["recall"],
        "atomic_claim_f1": lambda row: row["atomic_claims"]["f1"],
        "citation_correctness": lambda row: row["citation_correctness"],
        "citation_completeness": lambda row: row["citation_completeness"],
        "faithfulness": lambda row: row["faithfulness_to_retrieved_context"],
        "unanswerable_accuracy": lambda row: row["unanswerable_correct"],
        "answer_latency_seconds": lambda row: row["answer_latency_seconds"],
        "estimated_cost_usd": lambda row: row["estimated_cost_usd"],
    }
    output = []
    for group_index, ((mode, task_type), group) in enumerate(sorted(groups.items())):
        metrics = {}
        for metric_index, (name, getter) in enumerate(getters.items()):
            values = [value for row in group for value in [getter(row)] if value is not None]
            metrics[name] = bootstrap(values, samples, random.Random(seed + group_index * 101 + metric_index))
        output.append({"mode": mode, "task_type": task_type, "question_count": len(group), "metrics": metrics})
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--claim-threshold", type=float, default=0.72)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=39901)
    args = parser.parse_args()
    questions = index_by_id(load_jsonl(QUESTIONS_PATH), "question")
    rows = []
    for result in load_jsonl(args.results):
        question_id = result.get("question_id")
        if question_id not in questions:
            raise RuntimeError(f"Unknown question_id in results: {question_id}")
        if not result.get("prediction"):
            raise RuntimeError(
                f"Result {question_id}/{result.get('mode')} has no prediction. "
                "Do not run answer scoring on --retrieval-only output."
            )
        rows.append(score_row(result, questions[question_id], args.claim_threshold))
    payload = {"per_question": rows, "summaries": summaries(rows, args.bootstrap_samples, args.seed)}
    write_json(args.output, payload)
    print(f"answer score rows={len(rows)} report={args.output}")


if __name__ == "__main__":
    main()
