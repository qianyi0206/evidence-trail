#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from common import (
    ROOT,
    api_headers,
    ensure_index_compatible,
    lightrag_url,
    workspace_locked,
    workspace_state_path,
    write_json_atomic,
)


def get_documents(client: httpx.Client, env: dict[str, str]) -> list[dict]:
    response = client.get(lightrag_url(env, "/documents"), headers=api_headers(env))
    response.raise_for_status()
    return [
        document
        for documents in response.json().get("statuses", {}).values()
        for document in documents
    ]


def by_name(documents: list[dict]) -> dict[str, dict]:
    return {Path(item.get("file_path", "")).name: item for item in documents}


def load_bundle(env: dict[str, str]) -> tuple[Path, dict]:
    setting = env.get("GB39901_STRUCTURAL_UNITS_FILE", "").strip()
    if not setting:
        raise RuntimeError("GB39901_STRUCTURAL_UNITS_FILE is not configured")
    path = (ROOT / setting).resolve()
    path.relative_to(ROOT.resolve())
    bundle = json.loads(path.read_text(encoding="utf-8"))
    units = bundle.get("units", [])
    if not units or any(not unit.get("file_source") or not unit.get("content") for unit in units):
        raise RuntimeError("Structural bundle is empty or incomplete; run 'make v3-prepare'")
    if len({unit["file_source"] for unit in units}) != len(units):
        raise RuntimeError("Structural bundle file sources are not unique")
    return path, bundle


def wait_until_pipeline_idle(
    client: httpx.Client,
    env: dict[str, str],
    expected_names: set[str],
    deadline: float,
) -> dict[str, dict]:
    last_counts: tuple[int, int, int, int] | None = None
    while time.monotonic() < deadline:
        current = by_name(get_documents(client, env))
        visible = {name: current[name] for name in expected_names if name in current}
        counts = (
            sum(item.get("status") == "processed" for item in visible.values()),
            sum(item.get("status") == "processing" for item in visible.values()),
            sum(item.get("status") == "pending" for item in visible.values()),
            sum(item.get("status") == "failed" for item in visible.values()),
        )
        if counts != last_counts:
            print(
                "status     waiting for active queue: "
                f"processed={counts[0]}/{len(expected_names)} "
                f"processing={counts[1]} pending={counts[2]} failed={counts[3]}"
            )
            last_counts = counts
        if (
            len(visible) == len(expected_names)
            and counts[1] == 0
            and counts[2] == 0
        ):
            return visible
        time.sleep(5)
    raise RuntimeError("Timed out after 2 hours waiting for the active indexing queue to finish")


@workspace_locked
def main(env: dict[str, str]) -> None:
    bundle_path, bundle = load_bundle(env)
    units = bundle["units"]
    expected_names = {unit["file_source"] for unit in units}
    fingerprint_path = workspace_state_path(env, "embedding_fingerprint")
    report_path = workspace_state_path(env, "ingest_report")
    had_fingerprint = fingerprint_path.exists()
    current_fingerprint = ensure_index_compatible(env, fingerprint_path)
    submitted: list[str] = []
    reprocessed: list[str] = []
    mutation_started = False

    def mark_indexing() -> None:
        nonlocal mutation_started
        if mutation_started:
            return
        write_json_atomic(
            fingerprint_path,
            {
                **current_fingerprint,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "status": "indexing",
            },
        )
        mutation_started = True

    def mark_unverified(unexpected_documents: list[str]) -> None:
        write_json_atomic(
            fingerprint_path,
            {
                **current_fingerprint,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "status": "unverified",
                "reason": "workspace_contains_unexpected_documents",
                "unexpected_documents": unexpected_documents,
            },
        )

    with httpx.Client(timeout=180) as client:
        health = client.get(lightrag_url(env, "/health"), headers=api_headers(env))
        health.raise_for_status()
        documents = get_documents(client, env)
        if not had_fingerprint and any(
            item.get("status") in {"pending", "processing", "processed", "failed"}
            for item in documents
        ):
            raise RuntimeError(
                "The workspace contains documents but has no verified index fingerprint. "
                "Use a clean workspace or reset it before structural ingest."
            )
        existing = by_name(documents)
        unexpected = sorted(
            name
            for name, item in existing.items()
            if item.get("status") in {"pending", "processing", "processed", "failed"}
            and name not in expected_names
        )
        if unexpected:
            mark_unverified(unexpected)
            raise RuntimeError(
                "The v3 workspace contains non-structural documents: "
                f"{unexpected}. Use a clean workspace label."
            )

        active_names = {
            name
            for name in expected_names
            if existing.get(name, {}).get("status") in {"pending", "processing"}
        }
        if active_names:
            mark_indexing()
            print(
                f"ingest-v3  waiting for the existing active queue "
                f"({len(active_names)} structural units)"
            )
            wait_until_pipeline_idle(
                client, env, active_names, time.monotonic() + 7200
            )
            existing = by_name(get_documents(client, env))

        missing_units = [unit for unit in units if unit["file_source"] not in existing]
        if missing_units:
            mark_indexing()
            response = client.post(
                lightrag_url(env, "/documents/texts"),
                headers=api_headers(env),
                json={
                    "texts": [unit["content"] for unit in missing_units],
                    "file_sources": [unit["file_source"] for unit in missing_units],
                },
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("status") != "success":
                raise RuntimeError(f"Structural submission was rejected: {payload}")
            submitted = [unit["file_source"] for unit in missing_units]
            print(f"ingest-v3  queued {len(submitted)} structural units")
        else:
            print("ingest-v3  all structural units are already registered")

        recovery_round = 0
        deadline = time.monotonic() + 7200
        while True:
            final_documents = wait_until_pipeline_idle(
                client, env, expected_names, deadline
            )
            failed = {
                name: item.get("error_msg")
                for name, item in final_documents.items()
                if item.get("status") == "failed"
            }
            non_processed = {
                name: item.get("status")
                for name, item in final_documents.items()
                if item.get("status") != "processed"
            }
            if not failed and not non_processed:
                break
            if not failed:
                raise RuntimeError(f"Structural documents did not settle: {non_processed}")
            recovery_round += 1
            if recovery_round > 3:
                raise RuntimeError(
                    f"Structural indexing still failed after 3 recovery rounds: {failed}"
                )
            retry_names = sorted(failed)
            reprocessed.extend(name for name in retry_names if name not in reprocessed)
            mark_indexing()
            response = client.post(
                lightrag_url(env, "/documents/reprocess_failed"),
                headers=api_headers(env),
            )
            response.raise_for_status()
            print(
                f"ingest-v3  recovery round {recovery_round}: "
                f"retrying {len(retry_names)} failed structural units"
            )
            time.sleep(2)

    split_documents = {
        name: item.get("chunks_count")
        for name, item in final_documents.items()
        if item.get("chunks_count") != 1
    }
    if split_documents:
        raise RuntimeError(
            "Atomic unit invariant failed: each structural document must produce exactly one "
            f"LightRAG chunk, found {split_documents}"
        )

    recorded_at = datetime.now(timezone.utc).isoformat()
    write_json_atomic(
        fingerprint_path,
        {
            **current_fingerprint,
            "recorded_at": recorded_at,
            "status": "ready",
        },
    )
    write_json_atomic(
        report_path,
        {
            "completed_at": recorded_at,
            "strategy": bundle.get("strategy"),
            "bundle_file": str(bundle_path.relative_to(ROOT)),
            "bundle_sha256": current_fingerprint["corpus"]["inputs"][
                "bundle_sha256"
            ],
            "source_sha256": bundle.get("source_sha256"),
            "corpus": current_fingerprint["corpus"],
            "submitted": submitted,
            "reprocessed": reprocessed,
            "documents": list(final_documents.values()),
            "atomic_chunk_invariant": True,
        },
    )
    print(
        f"ingest-v3  OK ({len(final_documents)} documents, "
        "exactly one LightRAG chunk per structural unit)"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ingest-v3  FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
