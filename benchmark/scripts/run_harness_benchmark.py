#!/usr/bin/env python3
"""Run regulation harness on GB benchmark questions and emit score_answers-compatible rows.

Offline gold is used only for scoring after the run — never injected into the agent.
Cross-document questions are skipped (need multi-doc workspace).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
BENCHMARK_ROOT = SCRIPT_DIR.parent
AEB_ROOT = BENCHMARK_ROOT.parent
HARNESS_ROOT = AEB_ROOT / "harness"
QUESTIONS_PATH = BENCHMARK_ROOT / "data" / "questions.jsonl"

if str(HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(HARNESS_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def done_ids(path: Path, mode: str) -> set[str]:
    out: set[str] = set()
    for row in load_jsonl(path):
        if row.get("mode") == mode and row.get("question_id"):
            out.add(str(row["question_id"]))
    return out


def select_questions(
    *,
    source: str,
    split: str | None,
    limit: int | None,
    only_ids: list[str] | None,
) -> list[dict[str, Any]]:
    questions = load_jsonl(QUESTIONS_PATH)
    selected = []
    for q in questions:
        qid = str(q["id"])
        if only_ids and qid not in only_ids:
            continue
        if source == "gb" and not qid.startswith("gb_"):
            continue
        if source == "cross" and not qid.startswith("cross_"):
            continue
        if split and q.get("split") != split:
            continue
        selected.append(q)
    if limit is not None:
        selected = selected[: max(0, limit)]
    return selected


def state_to_result_row(
    question: dict[str, Any],
    state: Any,
    *,
    mode: str,
    latency: float,
    error: str | None = None,
) -> dict[str, Any]:
    final = getattr(state, "final_answer", None) if state is not None else None
    if not isinstance(final, dict):
        final = {
            "answerable": False,
            "answer": {},
            "claims": [],
            "citations": [],
            "reason": error or "no_final_answer",
        }
    prediction = {
        "answerable": final.get("answerable"),
        "answer": final.get("answer") if final.get("answer") is not None else {},
        "claims": final.get("claims") or [],
        "citations": final.get("citations") or [],
        "reason": final.get("reason") or "",
        "validation_flags": final.get("validation_flags") or [],
    }
    evidence_ids: list[str] = []
    retrieved_items: list[dict[str, Any]] = []
    if state is not None:
        for index, item in enumerate(getattr(state, "evidence", []) or [], 1):
            ids = [str(x) for x in (getattr(item, "evidence_ids", None) or []) if x]
            evidence_ids.extend(ids)
            retrieved_items.append(
                {
                    "rank": index,
                    "kind": getattr(item, "kind", "") or "",
                    "file_path": getattr(item, "file_path", "") or "",
                    "evidence_ids": ids,
                    "text": getattr(item, "text", "") or "",
                }
            )
    evidence_ids = sorted(set(str(x) for x in evidence_ids if x))
    trace_events = []
    steps = 0
    bag = 0
    if state is not None:
        steps = int(getattr(state, "step", 0) or 0)
        bag = len(getattr(state, "evidence", []) or [])
        for event in getattr(state, "trace", []) or []:
            if isinstance(event, dict):
                trace_events.append(event.get("event"))
    return {
        "question_id": question["id"],
        "mode": mode,
        "split": question.get("split"),
        "task_type": question.get("task_type"),
        "scoring_method": question.get("scoring_method"),
        "answerable_gold": question.get("answerable"),
        "prediction": prediction,
        "citations": prediction.get("citations") or [],
        "retrieved_evidence_ids": evidence_ids,
        "ranked_evidence_ids": evidence_ids,
        "retrieved_items": retrieved_items,
        "answer_latency_seconds": latency,
        "retrieval_latency_seconds": 0.0,
        "answer_cost_usd": None,
        "retrieval_cost_usd": None,
        "harness_steps": steps,
        "harness_evidence_count": bag,
        "harness_trace_events": trace_events,
        "error": error,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile-env",
        default=".env.gb39901_v4",
        help="Profile under demo/aeb (default .env.gb39901_v4)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=BENCHMARK_ROOT / "results" / "run_harness_skill_gb50.jsonl",
    )
    parser.add_argument("--mode-name", default="harness_skill")
    parser.add_argument("--source", choices=("gb", "cross", "all"), default="gb")
    parser.add_argument("--split", default=None, help="dev|test")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--question-id", action="append", default=None)
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--resume", action="store_true", default=True)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument(
        "--score-output",
        type=Path,
        default=BENCHMARK_ROOT / "results" / "answer_score_harness_skill_gb50.json",
    )
    parser.add_argument("--skip-score", action="store_true")
    parser.add_argument(
        "--claim-threshold",
        type=float,
        default=0.72,
        help="Claim matching threshold (must match score_answers default 0.72)",
    )
    args = parser.parse_args()

    resume = bool(args.resume) and not bool(args.no_resume)
    questions = select_questions(
        source=args.source,
        split=args.split,
        limit=args.limit,
        only_ids=args.question_id,
    )
    if not questions:
        print("No questions selected.", file=sys.stderr)
        return 1

    finished = done_ids(args.output, args.mode_name) if resume else set()
    pending = [q for q in questions if q["id"] not in finished]
    print(
        f"selected={len(questions)} done={len(finished)} pending={len(pending)} "
        f"output={args.output} profile={args.profile_env}",
        flush=True,
    )

    from reg_harness.runtime import build_stack
    from reg_harness.loop import state_to_dict

    stack = build_stack(profile_env=args.profile_env)
    print(f"stack={json.dumps(stack.describe(), ensure_ascii=False)}", flush=True)

    failures = 0
    for index, question in enumerate(pending, 1):
        qid = question["id"]
        text = question["question"]
        print(
            f"[{index}/{len(pending)}] {qid} type={question.get('task_type')} "
            f"method={question.get('scoring_method')}",
            flush=True,
        )
        started = time.time()
        state = None
        error = None
        try:
            state = stack.ask(
                text,
                policy="auto",
                max_steps=args.max_steps,
                bootstrap=False,
            )
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
            failures += 1
            traceback.print_exc()
        latency = time.time() - started
        row = state_to_result_row(
            question, state, mode=args.mode_name, latency=latency, error=error
        )
        # Keep a compact trace dump for debugging without blowing up jsonl size.
        if state is not None:
            compact = state_to_dict(state)
            compact.pop("trace", None)
            row["harness_summary"] = {
                "steps": compact.get("steps"),
                "evidence_count": compact.get("evidence_count"),
                "done": compact.get("done"),
                "phase": compact.get("phase"),
                "refuse_reason": compact.get("refuse_reason"),
            }
        append_jsonl(args.output, row)
        pred = row["prediction"]
        print(
            f"  -> answerable={pred.get('answerable')} steps={row.get('harness_steps')} "
            f"bag={row.get('harness_evidence_count')} latency={latency:.1f}s error={error}",
            flush=True,
        )

    print(f"run complete failures={failures} total_rows={len(load_jsonl(args.output))}", flush=True)

    if args.skip_score:
        return 0 if failures == 0 else 2

    # Score with official scorer.
    from score_answers import score_row, summaries  # type: ignore
    from benchmark_common import index_by_id, write_json  # type: ignore

    gold = index_by_id(load_jsonl(QUESTIONS_PATH), "question")
    rows = []
    for result in load_jsonl(args.output):
        if result.get("mode") != args.mode_name:
            continue
        qid = result.get("question_id")
        if qid not in gold:
            continue
        if not result.get("prediction"):
            continue
        try:
            rows.append(
                score_row(result, gold[qid], claim_threshold=args.claim_threshold)
            )
        except Exception as exc:  # noqa: BLE001
            print(f"score failed {qid}: {exc}", file=sys.stderr)
    payload = {
        "mode": args.mode_name,
        "source": args.source,
        "claim_threshold": args.claim_threshold,
        "per_question": rows,
        "summaries": summaries(rows, samples=1000, seed=39901),
        "results_path": str(args.output),
    }
    write_json(args.score_output, payload)

    # Human-readable rollup
    by_type: dict[str, list[float]] = {}
    answerable_match = 0
    for row in rows:
        by_type.setdefault(row["task_type"], []).append(float(row["primary_score"]))
        gold_a = bool(row["answerable"])
        pred_a = (row.get("prediction") or {}).get("answerable")
        if pred_a is None:
            pred_a = True
        if bool(pred_a) == gold_a:
            answerable_match += 1
    overall = [float(r["primary_score"]) for r in rows]
    mean = sum(overall) / len(overall) if overall else 0.0
    print("\n===== SCORE SUMMARY =====")
    print(f"n={len(rows)} primary_mean={mean:.3f} answerable_match={answerable_match}/{len(rows)}")
    for task, vals in sorted(by_type.items()):
        print(f"  {task}: n={len(vals)} mean={sum(vals)/len(vals):.3f}")
    print(f"score_json={args.score_output}")
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
