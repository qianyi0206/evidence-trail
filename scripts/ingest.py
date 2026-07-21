from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from common import (
    MANIFEST_PATH,
    ROOT,
    STATE_DIR,
    active_documents,
    api_headers,
    embedding_fingerprint,
    ingest_path_for_record,
    lightrag_url,
    load_env,
    workspace_state_path,
    write_json_atomic,
)

def get_documents(client: httpx.Client, env: dict[str, str]) -> list[dict]:
    response = client.get(lightrag_url(env, "/documents"), headers=api_headers(env))
    response.raise_for_status()
    statuses = response.json().get("statuses", {})
    return [document for documents in statuses.values() for document in documents]


def ensure_fingerprint_compatible(env: dict[str, str], fingerprint_path: Path) -> dict:
    current = embedding_fingerprint(env)
    if fingerprint_path.exists():
        stored = json.loads(fingerprint_path.read_text(encoding="utf-8"))
        if stored.get("sha256") != current["sha256"]:
            raise RuntimeError(
                "Embedding configuration changed after indexing. Refusing to mix vector spaces. "
                "Restore the original settings or explicitly run "
                "'make reset-index CONFIRM=RESET_AEB_INDEX'."
            )
    return current


def main() -> None:
    env = load_env()
    fingerprint_path = workspace_state_path(env, "embedding_fingerprint")
    report_path = workspace_state_path(env, "ingest_report")
    current_fingerprint = ensure_fingerprint_compatible(env, fingerprint_path)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    records = active_documents(manifest)
    if any("prepared_file" not in item for item in records):
        raise RuntimeError("Prepared corpus is incomplete. Run 'make prepare' first.")
    missing_files = [str(ingest_path_for_record(env, item)) for item in records if not ingest_path_for_record(env, item).is_file()]
    if missing_files:
        raise RuntimeError(f"Prepared corpus files are missing: {missing_files}")

    expected_names = {Path(item["prepared_file"]).name for item in records}
    uploads: list[dict] = []
    with httpx.Client(timeout=120) as client:
        health = client.get(lightrag_url(env, "/health"), headers=api_headers(env))
        health.raise_for_status()

        existing_documents = get_documents(client, env)
        unexpected = sorted(
            Path(item.get("file_path", "")).name
            for item in existing_documents
            if item.get("status") in {"pending", "processing", "processed"}
            and Path(item.get("file_path", "")).name not in expected_names
        )
        if unexpected:
            raise RuntimeError(
                "The workspace already contains non-enabled documents: "
                f"{unexpected}. Reset the AEB index before single-document ingestion."
            )
        existing = {
            Path(item.get("file_path", "")).name: item
            for item in existing_documents
        }
        reprocess_failed = False
        for record in records:
            path = ingest_path_for_record(env, record)
            upload_name = Path(record["prepared_file"]).name
            if upload_name in existing:
                existing_status = existing[upload_name].get("status")
                if existing_status == "processed":
                    uploads.append({"file": upload_name, "status": "already_processed"})
                    print(f"ingest     kept {upload_name} (already processed)")
                    continue
                if existing_status == "failed":
                    uploads.append({"file": upload_name, "status": "queued_for_reprocess"})
                    reprocess_failed = True
                    print(f"ingest     retry {upload_name} (cached failed document)")
                    continue
                if existing_status in {"pending", "processing"}:
                    uploads.append({"file": upload_name, "status": f"already_{existing_status}"})
                    print(f"ingest     kept {upload_name} ({existing_status})")
                    continue

            with path.open("rb") as handle:
                response = client.post(
                    lightrag_url(env, "/documents/upload"),
                    headers=api_headers(env),
                    files={"file": (upload_name, handle, "text/markdown")},
                )
            response.raise_for_status()
            payload = response.json()
            uploads.append({"file": upload_name, **payload})
            print(f"ingest     queued {upload_name}: {payload.get('status')}")

        if reprocess_failed:
            response = client.post(
                lightrag_url(env, "/documents/reprocess_failed"),
                headers=api_headers(env),
            )
            response.raise_for_status()
            print(f"ingest     reprocess: {response.json().get('status')}")

        deadline = time.monotonic() + 7200
        reprocess_grace_deadline = time.monotonic() + 120 if reprocess_failed else 0
        last_summary = None
        final_documents: dict[str, dict] = {}
        while time.monotonic() < deadline:
            documents = get_documents(client, env)
            final_documents = {
                Path(item.get("file_path", "")).name: item
                for item in documents
                if Path(item.get("file_path", "")).name in expected_names
            }
            summary = {
                name: final_documents.get(name, {}).get("status", "not_visible")
                for name in sorted(expected_names)
            }
            if summary != last_summary:
                print("status     " + ", ".join(f"{name}={status}" for name, status in summary.items()))
                last_summary = summary

            failed = [name for name, item in final_documents.items() if item.get("status") == "failed"]
            if failed:
                if time.monotonic() < reprocess_grace_deadline:
                    time.sleep(5)
                    continue
                details = {name: final_documents[name].get("error_msg") for name in failed}
                raise RuntimeError(f"Document indexing failed: {details}")
            if len(final_documents) == len(expected_names) and all(
                item.get("status") == "processed" for item in final_documents.values()
            ):
                break
            time.sleep(5)
        else:
            raise RuntimeError("Timed out after 2 hours waiting for document indexing")

    fingerprint_record = {
        **current_fingerprint,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json_atomic(fingerprint_path, fingerprint_record)
    write_json_atomic(
        report_path,
        {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "uploads": uploads,
            "documents": list(final_documents.values()),
        },
    )
    print(f"ingest     OK ({len(final_documents)} documents processed)")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ingest     FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
