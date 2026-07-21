#!/usr/bin/env python3
"""Freeze a reviewed benchmark release and write a checksum manifest."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmark_common import (
    AUDIT_PATH,
    BENCHMARK_ROOT,
    EVIDENCE_PATH,
    GRAPH_PATH,
    QUESTIONS_PATH,
    index_by_id,
    load_jsonl,
    sha256_file,
    write_json,
    write_jsonl,
)


def reviewed_rows(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file():
        raise RuntimeError(f"Missing review file: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    indexed = index_by_id(rows, "review")
    decisions = Counter(str(row.get("review_decision", "")).strip() for row in rows)
    if decisions != Counter({"通过": len(rows)}):
        raise RuntimeError(
            "Benchmark cannot be frozen until all rows are marked 通过. "
            f"Current decisions: {dict(decisions)}"
        )
    return indexed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="v1")
    parser.add_argument("--review", type=Path, default=BENCHMARK_ROOT / "review" / "benchmark_review.csv")
    args = parser.parse_args()
    if not args.version or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for character in args.version):
        raise SystemExit("Unsafe --version")
    reviews = reviewed_rows(args.review)
    questions = load_jsonl(QUESTIONS_PATH)
    if set(reviews) != {item["id"] for item in questions}:
        raise RuntimeError("Review rows and benchmark questions do not have identical IDs")
    frozen_questions = []
    for question in questions:
        frozen = dict(question)
        frozen["review_status"] = "frozen"
        frozen["user_review"] = {
            "decision": "通过",
            "notes": reviews[question["id"]].get("review_notes", "").strip(),
        }
        frozen_questions.append(frozen)
    release = BENCHMARK_ROOT / "releases" / args.version
    if release.exists():
        raise RuntimeError(f"Release already exists and will not be overwritten: {release}")
    data_dir = release / "data"
    write_jsonl(data_dir / "evidence.jsonl", load_jsonl(EVIDENCE_PATH))
    write_jsonl(data_dir / "questions.jsonl", frozen_questions)
    write_jsonl(data_dir / "task_graph.jsonl", load_jsonl(GRAPH_PATH))
    write_jsonl(data_dir / "audit_units.jsonl", load_jsonl(AUDIT_PATH))
    files = sorted(data_dir.glob("*.jsonl"))
    manifest: dict[str, Any] = {
        "benchmark": "GB 39901 GraphRAG Benchmark",
        "version": args.version,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "question_count": len(frozen_questions),
        "review_file_sha256": sha256_file(args.review),
        "files": [
            {"path": str(path.relative_to(release)), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for path in files
        ],
        "source_files": sorted(
            {
                (item["source_file"], item["source_sha256"])
                for item in load_jsonl(EVIDENCE_PATH)
            }
        ),
    }
    write_json(release / "manifest.json", manifest)
    print(f"frozen version={args.version} questions={len(frozen_questions)} release={release}")


if __name__ == "__main__":
    main()
