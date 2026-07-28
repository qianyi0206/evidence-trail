#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from benchmark_common import (
    AEB_ROOT,
    AUDIT_PATH,
    EVIDENCE_PATH,
    GRAPH_PATH,
    QUESTIONS_PATH,
    REVIEW_DIR,
    SCHEMA_PATH,
    index_by_id,
    load_jsonl,
    normalize_text,
    review_content_sha256,
    sha256_file,
)
from benchmark_contract import (
    KG_RELATION_ENDPOINTS,
    KG_SCHEMA_TYPES,
    evidence_source_ids,
    graph_edge_is_schema_legal,
    question_source_ids,
)
from json_schema_validator import load_schema, validate_definition

EXPECTED_TASK_COUNTS = {
    "direct_fact": 8,
    "conditional_table": 10,
    "multi_hop_relation": 12,
    "comparison_exception": 8,
    "cross_section_synthesis": 6,
    "unanswerable_adversarial": 6,
    "cross_document_alignment": 4,
    "cross_document_comparison": 3,
    "cross_document_synthesis": 2,
    "cross_document_unanswerable": 1,
}

GRAPH_REQUIRED_TASKS = {
    "multi_hop_relation",
    "comparison_exception",
    "cross_section_synthesis",
    "cross_document_alignment",
    "cross_document_comparison",
    "cross_document_synthesis",
}

PUBLISHED_PILOT_IDS = {
    "gb_direct_001",
    "gb_table_002",
    "gb_multi_hop_009",
    "gb_compare_002",
    "gb_synthesis_001",
    "gb_unanswerable_002",
}

def fail(message: str, errors: list[str]) -> None:
    errors.append(message)


def validate_evidence(records: list[dict[str, Any]], errors: list[str]) -> dict[str, dict[str, Any]]:
    evidence = index_by_id(records, "evidence")
    source_cache: dict[Path, str] = {}
    source_hash_cache: dict[Path, str] = {}
    for record_id, record in evidence.items():
        for required in ("source_id", "source_file", "locator", "title", "source_excerpt", "source_sha256"):
            if not record.get(required):
                fail(f"Evidence {record_id} lacks {required}", errors)
        source_path = (AEB_ROOT / str(record.get("source_file", ""))).resolve()
        try:
            source_path.relative_to(AEB_ROOT.resolve())
        except ValueError:
            fail(f"Evidence {record_id} escapes AEB root: {source_path}", errors)
            continue
        if not source_path.is_file():
            fail(f"Evidence {record_id} source file is missing: {source_path}", errors)
            continue
        if source_path not in source_cache:
            source_cache[source_path] = source_path.read_text(encoding="utf-8")
            source_hash_cache[source_path] = sha256_file(source_path)
        if record.get("source_sha256") != source_hash_cache[source_path]:
            fail(f"Evidence {record_id} source SHA-256 mismatch", errors)
        excerpt = normalize_text(record.get("source_excerpt", ""))
        is_table_row = bool(record.get("locator", {}).get("table") and record.get("locator", {}).get("row"))
        if len(excerpt) < 8 and not (is_table_row and len(record.get("source_excerpt", "")) >= 100):
            fail(f"Evidence {record_id} excerpt is too short", errors)
        elif excerpt not in normalize_text(source_cache[source_path]):
            fail(f"Evidence {record_id} excerpt cannot be found in source", errors)
    return evidence


def validate_graph(
    records: list[dict[str, Any]],
    evidence: dict[str, dict[str, Any]],
    errors: list[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    nodes = index_by_id((item for item in records if item.get("kind") == "node"), "graph node")
    edges = index_by_id((item for item in records if item.get("kind") == "edge"), "graph edge")
    if len(nodes) + len(edges) != len(records):
        fail("Graph contains records whose kind is neither node nor edge", errors)
    for node_id, node in nodes.items():
        if not node.get("type") or not node.get("name"):
            fail(f"Node {node_id} lacks type or name", errors)
        for evidence_id in node.get("evidence_ids", []):
            if evidence_id not in evidence:
                fail(f"Node {node_id} references missing evidence {evidence_id}", errors)
        if node.get("properties", {}).get("graph_role") == "extractable_kg" and node.get("type") not in KG_SCHEMA_TYPES:
            fail(f"Audit node {node_id} has non-schema type {node.get('type')}", errors)
    for edge_id, edge in edges.items():
        if edge.get("source") not in nodes or edge.get("target") not in nodes:
            fail(f"Edge {edge_id} has missing endpoint", errors)
        if not edge.get("relation"):
            fail(f"Edge {edge_id} lacks relation", errors)
        if not edge.get("evidence_ids"):
            fail(f"Edge {edge_id} lacks evidence", errors)
        for evidence_id in edge.get("evidence_ids", []):
            if evidence_id not in evidence:
                fail(f"Edge {edge_id} references missing evidence {evidence_id}", errors)
        if edge.get("properties", {}).get("graph_role") == "extractable_kg":
            relation = edge.get("relation")
            if relation not in KG_RELATION_ENDPOINTS:
                fail(f"Audit edge {edge_id} has unsupported schema relation {relation}", errors)
            elif edge.get("source") in nodes and edge.get("target") in nodes:
                allowed_source, allowed_target = KG_RELATION_ENDPOINTS[relation]
                source_type = nodes[edge["source"]].get("type")
                target_type = nodes[edge["target"]].get("type")
                if source_type not in allowed_source or target_type not in allowed_target:
                    fail(f"Audit edge {edge_id} invalid endpoints {source_type}->{target_type} for {relation}", errors)
    return nodes, edges


def validate_questions(
    records: list[dict[str, Any]],
    evidence: dict[str, dict[str, Any]],
    nodes: dict[str, dict[str, Any]],
    edges: dict[str, dict[str, Any]],
    errors: list[str],
    allow_partial: bool,
) -> dict[str, dict[str, Any]]:
    questions = index_by_id(records, "question")
    task_counts = Counter(item.get("task_type") for item in records)
    if not allow_partial:
        if len(records) != 60:
            fail(f"Expected 60 questions, found {len(records)}", errors)
        for task_type, expected in EXPECTED_TASK_COUNTS.items():
            if task_counts[task_type] != expected:
                fail(f"Expected {expected} {task_type} questions, found {task_counts[task_type]}", errors)
        split_counts = Counter(item.get("split") for item in records)
        if split_counts != Counter({"dev": 12, "test": 48}):
            fail(f"Expected split dev=12/test=48, found {dict(split_counts)}", errors)

    for question_id, question in questions.items():
        required = (
            "question",
            "task_type",
            "answerable",
            "gold_answer",
            "atomic_claims",
            "gold_evidence_ids",
            "gold_nodes",
            "gold_edges",
            "gold_path",
            "gold_reasoning_path",
            "gold_kg_path",
            "gold_kg_schema",
            "expected_hops",
            "expected_kg_hops",
            "graph_dependency_reason",
            "scoring_method",
            "review_status",
            "split",
            "self_review",
        )
        for field in required:
            if field not in question:
                fail(f"Question {question_id} lacks {field}", errors)
        if question.get("review_status") not in {"self_checked", "user_reviewed", "frozen"}:
            fail(f"Question {question_id} has invalid review status", errors)
        if question.get("split") not in {"dev", "test"}:
            fail(f"Question {question_id} has invalid split", errors)
        if question_id in PUBLISHED_PILOT_IDS and question.get("split") != "dev":
            fail(
                f"Published pilot question {question_id} must remain in dev",
                errors,
            )
        if not question.get("graph_dependency_reason"):
            fail(f"Question {question_id} lacks graph-dependency analysis", errors)

        question_evidence = set(question.get("gold_evidence_ids", []))
        for evidence_id in question_evidence:
            if evidence_id not in evidence:
                fail(f"Question {question_id} references missing evidence {evidence_id}", errors)
        for node_id in question.get("gold_nodes", []):
            if node_id not in nodes:
                fail(f"Question {question_id} references missing node {node_id}", errors)
        for edge_id in question.get("gold_edges", []):
            if edge_id not in edges:
                fail(f"Question {question_id} references missing edge {edge_id}", errors)

        path = question.get("gold_reasoning_path", [])
        if question.get("gold_path") != path:
            fail(
                f"Question {question_id} compatibility gold_path differs from gold_reasoning_path",
                errors,
            )
        if question.get("expected_hops") != len(path):
            fail(f"Question {question_id} expected_hops does not match path length", errors)
        if not set(path).issubset(set(question.get("gold_edges", []))):
            fail(f"Question {question_id} path is not a subset of gold_edges", errors)
        if question.get("task_type") in GRAPH_REQUIRED_TASKS and len(path) < 2:
            fail(f"Graph-dependent question {question_id} has fewer than two hops", errors)
        for left_id, right_id in zip(path, path[1:]):
            left = edges.get(left_id, {})
            right = edges.get(right_id, {})
            if left.get("target") != right.get("source"):
                fail(f"Question {question_id} has disconnected path {left_id} -> {right_id}", errors)

        kg_path = question.get("gold_kg_path", [])
        if question.get("expected_kg_hops") != len(kg_path):
            fail(
                f"Question {question_id} expected_kg_hops does not match gold_kg_path",
                errors,
            )
        if not set(kg_path).issubset(set(question.get("gold_edges", []))):
            fail(
                f"Question {question_id} gold_kg_path is not a subset of gold_edges",
                errors,
            )
        if kg_path and question.get("gold_kg_schema") != "gb39901_v4":
            fail(
                f"Question {question_id} has gold_kg_path without gb39901_v4 schema",
                errors,
            )
        if not kg_path and question.get("gold_kg_schema") is not None:
            fail(
                f"Question {question_id} has gold_kg_schema but no gold_kg_path",
                errors,
            )
        question_sources = question_source_ids(question)
        expected_kg_path = []
        if question_sources == {"gb39901"} and all(
            edge_id in edges
            and graph_edge_is_schema_legal(edges[edge_id], nodes)
            and evidence_source_ids(
                list(edges[edge_id].get("evidence_ids", [])),
                evidence,
            ).issubset(question_sources)
            for edge_id in path
        ):
            expected_kg_path = path
        if kg_path != expected_kg_path:
            fail(
                f"Question {question_id} gold_kg_path must be the complete "
                "schema-legal, source-matched reasoning path or empty",
                errors,
            )

        claim_ids: set[str] = set()
        for claim in question.get("atomic_claims", []):
            claim_id = str(claim.get("id", ""))
            if not claim_id or claim_id in claim_ids:
                fail(f"Question {question_id} has missing/duplicate claim id", errors)
            claim_ids.add(claim_id)
            claim_evidence = set(claim.get("evidence_ids", []))
            if not claim.get("text") or not claim_evidence:
                fail(f"Question {question_id} claim {claim_id} lacks text/evidence", errors)
            if not claim_evidence.issubset(question_evidence):
                fail(f"Question {question_id} claim {claim_id} uses undeclared evidence", errors)
            evidence_support = normalize_text(
                "\n".join(
                    evidence[item]["source_title"]
                    + "\n"
                    + evidence[item]["title"]
                    + "\n"
                    + evidence[item]["source_excerpt"]
                    + "\n"
                    + json.dumps(evidence[item].get("normalized_facts", {}), ensure_ascii=False)
                    for item in claim_evidence
                    if item in evidence
                )
            )
            numeric_tokens = re.findall(r"(?<![A-Za-z0-9])\d+(?:\.\d+)?", str(claim.get("text", "")))
            for token in numeric_tokens:
                if normalize_text(token) not in evidence_support:
                    fail(
                        f"Question {question_id} claim {claim_id} numeric token {token} "
                        "is absent from its evidence",
                        errors,
                    )

        method = question.get("scoring_method")
        if method not in {"structured_exact_match", "set_f1", "claim_f1", "unanswerable"}:
            fail(f"Question {question_id} has invalid scoring method {method}", errors)
        if question.get("answerable") is False and method != "unanswerable":
            fail(f"Unanswerable question {question_id} must use unanswerable scoring", errors)
        if question.get("answerable") is True and not question.get("atomic_claims"):
            fail(f"Answerable question {question_id} has no atomic claims", errors)

        self_review = question.get("self_review", {})
        review_checks = {
            "source_context_read",
            "answer_rederived",
            "conditions_complete",
            "counterexample_checked",
            "single_chunk_sufficiency_checked",
            "mechanical_validation_passed",
        }
        if set(key for key, value in self_review.items() if value is True) != review_checks:
            fail(f"Question {question_id} has incomplete self-review checklist", errors)
    return questions


def validate_audit(
    records: list[dict[str, Any]],
    evidence: dict[str, dict[str, Any]],
    nodes: dict[str, dict[str, Any]],
    edges: dict[str, dict[str, Any]],
    errors: list[str],
    allow_partial: bool,
) -> None:
    units = index_by_id(records, "audit unit")
    if not allow_partial:
        if len(units) != 10:
            fail(f"Expected 10 audit units, found {len(units)}", errors)
        kinds = Counter(item.get("kind") for item in records)
        if kinds != Counter({"narrative": 5, "table": 5}):
            fail(f"Expected 5 narrative/5 table audit units, found {dict(kinds)}", errors)
    for unit_id, unit in units.items():
        if unit.get("evidence_id") not in evidence:
            fail(f"Audit unit {unit_id} references missing evidence", errors)
        for node_id in unit.get("gold_nodes", []):
            if node_id not in nodes:
                fail(f"Audit unit {unit_id} references missing node {node_id}", errors)
        for edge_id in unit.get("gold_edges", []):
            if edge_id not in edges:
                fail(f"Audit unit {unit_id} references missing edge {edge_id}", errors)


def write_review_csv(
    questions: dict[str, dict[str, Any]],
    evidence: dict[str, dict[str, Any]],
    nodes: dict[str, dict[str, Any]],
    edges: dict[str, dict[str, Any]],
) -> Path:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    output = REVIEW_DIR / "benchmark_review.csv"
    if output.is_file():
        with output.open("r", encoding="utf-8-sig", newline="") as existing_handle:
            existing_rows = list(csv.DictReader(existing_handle))
        if any(
            str(row.get("review_decision", "")).strip()
            or str(row.get("review_notes", "")).strip()
            for row in existing_rows
        ):
            current_hashes = {
                question_id: review_content_sha256(
                    question,
                    evidence,
                    nodes,
                    edges,
                )
                for question_id, question in questions.items()
            }
            stale = [
                str(row.get("id", ""))
                for row in existing_rows
                if row.get("id") not in current_hashes
                or row.get("content_sha256") != current_hashes[row["id"]]
            ]
            if stale:
                raise RuntimeError(
                    "Existing review decisions are stale for question content: "
                    f"{stale}. Preserve the old file for audit, then regenerate "
                    "and review those rows again."
                )
            print(f"review   preserved existing user decisions in {output}")
            return output
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "id",
                "content_sha256",
                "split",
                "task_type",
                "question",
                "gold_answer",
                "atomic_claims",
                "evidence",
                "gold_path",
                "graph_dependency_reason",
                "review_decision",
                "review_notes",
            ],
        )
        writer.writeheader()
        for question in questions.values():
            snippets = [
                (
                    f"[{evidence_id}] {evidence[evidence_id]['title']}\n"
                    f"定位：{json.dumps(evidence[evidence_id]['locator'], ensure_ascii=False)}\n"
                    f"规范化事实：{json.dumps(evidence[evidence_id].get('normalized_facts', {}), ensure_ascii=False)}\n"
                    f"原文：{evidence[evidence_id]['source_excerpt']}"
                )
                for evidence_id in question.get("gold_evidence_ids", [])
            ]
            writer.writerow(
                {
                    "id": question["id"],
                    "content_sha256": review_content_sha256(
                        question,
                        evidence,
                        nodes,
                        edges,
                    ),
                    "split": question["split"],
                    "task_type": question["task_type"],
                    "question": question["question"],
                    "gold_answer": json.dumps(question["gold_answer"], ensure_ascii=False),
                    "atomic_claims": "\n".join(item["text"] for item in question["atomic_claims"]),
                    "evidence": "\n".join(snippets),
                    "gold_path": " -> ".join(question["gold_path"]),
                    "graph_dependency_reason": question["graph_dependency_reason"],
                    "review_decision": "",
                    "review_notes": "",
                }
            )
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--write-review", action="store_true")
    args = parser.parse_args()

    errors: list[str] = []
    evidence_records = load_jsonl(EVIDENCE_PATH)
    graph_records = load_jsonl(GRAPH_PATH)
    question_records = load_jsonl(QUESTIONS_PATH)
    audit_records = load_jsonl(AUDIT_PATH)
    schema = load_schema(SCHEMA_PATH)
    errors.extend(
        validate_definition(
            evidence_records,
            schema=schema,
            definition="evidence",
            label="evidence",
        )
    )
    errors.extend(
        validate_definition(
            [item for item in graph_records if item.get("kind") == "node"],
            schema=schema,
            definition="node",
            label="graph node",
        )
    )
    errors.extend(
        validate_definition(
            [item for item in graph_records if item.get("kind") == "edge"],
            schema=schema,
            definition="edge",
            label="graph edge",
        )
    )
    errors.extend(
        validate_definition(
            question_records,
            schema=schema,
            definition="question",
            label="question",
        )
    )
    errors.extend(
        validate_definition(
            audit_records,
            schema=schema,
            definition="audit_unit",
            label="audit unit",
        )
    )
    evidence = validate_evidence(evidence_records, errors)
    nodes, edges = validate_graph(graph_records, evidence, errors)
    questions = validate_questions(
        question_records,
        evidence,
        nodes,
        edges,
        errors,
        args.allow_partial,
    )
    validate_audit(
        audit_records,
        evidence,
        nodes,
        edges,
        errors,
        args.allow_partial,
    )

    if errors:
        for error in errors:
            print(f"ERROR {error}")
        raise SystemExit(f"Benchmark validation failed with {len(errors)} error(s)")

    review_path = (
        write_review_csv(questions, evidence, nodes, edges)
        if args.write_review
        else None
    )
    print(
        f"benchmark OK evidence={len(evidence)} nodes={len(nodes)} edges={len(edges)} "
        f"questions={len(questions)}"
    )
    if review_path:
        print(f"review   written {review_path}")


if __name__ == "__main__":
    main()
