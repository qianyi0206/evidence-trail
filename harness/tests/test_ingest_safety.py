from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import ingest as ingest_script
from common import (
    corpus_fingerprint,
    ensure_index_compatible,
    workspace_lock,
    write_json_atomic,
)


class _Response:
    def __init__(self, payload: dict | None = None) -> None:
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _HealthFailureClient:
    def __init__(self, **_: object) -> None:
        pass

    def __enter__(self) -> "_HealthFailureClient":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def get(self, *_: object, **__: object) -> _Response:
        raise httpx.ConnectError("health unavailable")

    def post(self, *_: object, **__: object) -> _Response:
        raise AssertionError("a write request must not start after a failed health check")


class _UploadFailureClient:
    post_calls = 0

    def __init__(self, **_: object) -> None:
        pass

    def __enter__(self) -> "_UploadFailureClient":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def get(self, *_: object, **__: object) -> _Response:
        return _Response({"status": "ok"})

    def post(self, *_: object, **__: object) -> _Response:
        type(self).post_calls += 1
        raise httpx.ConnectError("upload interrupted")


class _ReadOnlyClient:
    def __init__(self, **_: object) -> None:
        pass

    def __enter__(self) -> "_ReadOnlyClient":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def get(self, *_: object, **__: object) -> _Response:
        return _Response({"status": "ok"})

    def post(self, *_: object, **__: object) -> _Response:
        raise AssertionError("already-processed ingest must not issue a write request")


def embedding_env(**extra: str) -> dict[str, str]:
    return {
        "WORKSPACE": "test_workspace",
        "EMBEDDING_BINDING": "openai",
        "EMBEDDING_BINDING_HOST": "https://embedding.example/v1",
        "EMBEDDING_MODEL": "test-embedding",
        "EMBEDDING_DIM": "8",
        "EMBEDDING_TOKEN_LIMIT": "1024",
        **extra,
    }


def write_structural_fixture(root: Path, content: str) -> Path:
    source = root / "corpus" / "prepared" / "source.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("source material\n", encoding="utf-8")
    bundle = root / "corpus" / "index_ready_v3" / "units.json"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_text(
        json.dumps(
            {
                "source_id": "source",
                "source_file": source.name,
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "units": [
                    {
                        "unit_id": "unit_1",
                        "content": content.rstrip() + "\n",
                        "sha256": hashlib.sha256(
                            content.rstrip().encode("utf-8")
                        ).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return bundle


def write_ingest_fixture(root: Path) -> tuple[Path, Path, Path, Path, dict]:
    prepared = root / "corpus" / "prepared" / "document.md"
    prepared.parent.mkdir(parents=True, exist_ok=True)
    prepared.write_text("prepared document\n", encoding="utf-8")
    manifest = root / "corpus" / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "source_id": "document",
                        "enabled": True,
                        "prepared_file": "corpus/prepared/document.md",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    fingerprint = root / "state" / "embedding_fingerprint.json"
    report = root / "state" / "ingest_report.json"
    current = {
        "schema_version": 2,
        "binding": "openai",
        "model": "test-embedding",
        "dimension": 8,
        "token_limit": 1024,
        "sha256": "embedding-fingerprint",
        "corpus": {
            "sha256": "corpus-fingerprint",
            "inputs": {"mode": "prepared_documents"},
        },
    }
    write_json_atomic(
        fingerprint,
        {
            **current,
            "recorded_at": "2026-01-01T00:00:00+00:00",
            "status": "ready",
        },
    )
    return manifest, prepared, fingerprint, report, current


class IngestSafetyTests(unittest.TestCase):
    def test_structural_fingerprint_changes_with_bundle_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = write_structural_fixture(root, "first")
            env = embedding_env(
                GB39901_STRUCTURAL_UNITS_FILE=str(bundle.relative_to(root))
            )
            first = corpus_fingerprint(env, root=root)
            write_structural_fixture(root, "second")
            second = corpus_fingerprint(env, root=root)
        self.assertNotEqual(first["sha256"], second["sha256"])
        self.assertNotEqual(
            first["inputs"]["bundle_sha256"],
            second["inputs"]["bundle_sha256"],
        )

    def test_legacy_index_fingerprint_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = write_structural_fixture(root, "content")
            env = embedding_env(
                GB39901_STRUCTURAL_UNITS_FILE=str(bundle.relative_to(root))
            )
            fingerprint_path = root / "state" / "embedding_fingerprint.json"
            write_json_atomic(fingerprint_path, {"sha256": "legacy"})
            with self.assertRaisesRegex(RuntimeError, "Legacy index fingerprint"):
                ensure_index_compatible(env, fingerprint_path, root=root)

    def test_interrupted_index_fingerprint_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = write_structural_fixture(root, "content")
            env = embedding_env(
                GB39901_STRUCTURAL_UNITS_FILE=str(bundle.relative_to(root))
            )
            fingerprint_path = root / "state" / "embedding_fingerprint.json"
            current = ensure_index_compatible(env, fingerprint_path, root=root)
            write_json_atomic(
                fingerprint_path,
                {**current, "status": "indexing"},
            )
            with self.assertRaisesRegex(RuntimeError, "not ready"):
                ensure_index_compatible(env, fingerprint_path, root=root)

    def test_workspace_lock_rejects_a_concurrent_ingest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = embedding_env()
            state_dir = Path(tmp) / "state"
            with workspace_lock(env, state_dir=state_dir):
                with self.assertRaisesRegex(RuntimeError, "workspace lock"):
                    with workspace_lock(env, state_dir=state_dir):
                        self.fail("a second lock unexpectedly succeeded")

    def test_atomic_json_writes_use_independent_temp_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "state.json"
            payloads = [{"writer": index, "data": "x" * 1024} for index in range(24)]
            with ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(lambda payload: write_json_atomic(target, payload), payloads))
            final_payload = json.loads(target.read_text(encoding="utf-8"))
            leftovers = list(target.parent.glob(f".{target.name}.*.tmp"))
        self.assertIn(final_payload, payloads)
        self.assertEqual(leftovers, [])

    def test_ready_fingerprint_survives_health_failure_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, prepared, fingerprint, report, current = write_ingest_fixture(root)
            before = fingerprint.read_bytes()

            def state_path(_: dict[str, str], stem: str) -> Path:
                return fingerprint if stem == "embedding_fingerprint" else report

            with (
                patch.object(ingest_script, "MANIFEST_PATH", manifest),
                patch.object(ingest_script, "workspace_state_path", side_effect=state_path),
                patch.object(
                    ingest_script,
                    "ensure_index_compatible",
                    return_value=current,
                ),
                patch.object(
                    ingest_script,
                    "ingest_path_for_record",
                    return_value=prepared,
                ),
                patch.object(ingest_script.httpx, "Client", _HealthFailureClient),
            ):
                with self.assertRaisesRegex(httpx.ConnectError, "health unavailable"):
                    ingest_script.main.__wrapped__(embedding_env())

            self.assertEqual(fingerprint.read_bytes(), before)
            self.assertFalse(report.exists())

    def test_upload_failure_after_write_starts_leaves_indexing_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, prepared, fingerprint, report, current = write_ingest_fixture(root)

            def state_path(_: dict[str, str], stem: str) -> Path:
                return fingerprint if stem == "embedding_fingerprint" else report

            _UploadFailureClient.post_calls = 0
            with (
                patch.object(ingest_script, "MANIFEST_PATH", manifest),
                patch.object(ingest_script, "workspace_state_path", side_effect=state_path),
                patch.object(
                    ingest_script,
                    "ensure_index_compatible",
                    return_value=current,
                ),
                patch.object(
                    ingest_script,
                    "ingest_path_for_record",
                    return_value=prepared,
                ),
                patch.object(ingest_script, "get_documents", return_value=[]),
                patch.object(ingest_script.httpx, "Client", _UploadFailureClient),
            ):
                with self.assertRaisesRegex(httpx.ConnectError, "upload interrupted"):
                    ingest_script.main.__wrapped__(embedding_env())

            stored = json.loads(fingerprint.read_text(encoding="utf-8"))
            self.assertEqual(_UploadFailureClient.post_calls, 1)
            self.assertEqual(stored["status"], "indexing")
            self.assertFalse(report.exists())

    def test_existing_processing_document_marks_indexing_before_poll(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, prepared, fingerprint, report, current = write_ingest_fixture(root)

            def state_path(_: dict[str, str], stem: str) -> Path:
                return fingerprint if stem == "embedding_fingerprint" else report

            processing = [{"file_path": str(prepared), "status": "processing"}]
            with (
                patch.object(ingest_script, "MANIFEST_PATH", manifest),
                patch.object(ingest_script, "workspace_state_path", side_effect=state_path),
                patch.object(
                    ingest_script,
                    "ensure_index_compatible",
                    return_value=current,
                ),
                patch.object(
                    ingest_script,
                    "ingest_path_for_record",
                    return_value=prepared,
                ),
                patch.object(
                    ingest_script,
                    "get_documents",
                    side_effect=[
                        processing,
                        httpx.ConnectError("status poll interrupted"),
                    ],
                ),
                patch.object(ingest_script.httpx, "Client", _ReadOnlyClient),
            ):
                with self.assertRaisesRegex(
                    httpx.ConnectError,
                    "status poll interrupted",
                ):
                    ingest_script.main.__wrapped__(embedding_env())

            stored = json.loads(fingerprint.read_text(encoding="utf-8"))
            self.assertEqual(stored["status"], "indexing")
            self.assertFalse(report.exists())

    def test_unexpected_document_invalidates_ready_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, prepared, fingerprint, report, current = write_ingest_fixture(root)

            def state_path(_: dict[str, str], stem: str) -> Path:
                return fingerprint if stem == "embedding_fingerprint" else report

            unexpected = [{"file_path": "/remote/unexpected.md", "status": "processed"}]
            with (
                patch.object(ingest_script, "MANIFEST_PATH", manifest),
                patch.object(ingest_script, "workspace_state_path", side_effect=state_path),
                patch.object(
                    ingest_script,
                    "ensure_index_compatible",
                    return_value=current,
                ),
                patch.object(
                    ingest_script,
                    "ingest_path_for_record",
                    return_value=prepared,
                ),
                patch.object(ingest_script, "get_documents", return_value=unexpected),
                patch.object(ingest_script.httpx, "Client", _ReadOnlyClient),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "non-enabled documents",
                ):
                    ingest_script.main.__wrapped__(embedding_env())

            stored = json.loads(fingerprint.read_text(encoding="utf-8"))
            self.assertEqual(stored["status"], "unverified")
            self.assertEqual(
                stored["reason"],
                "workspace_contains_unexpected_documents",
            )
            self.assertEqual(stored["unexpected_documents"], ["unexpected.md"])
            self.assertFalse(report.exists())

    def test_already_processed_ingest_only_refreshes_ready_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, prepared, fingerprint, report, current = write_ingest_fixture(root)
            fingerprint_statuses: list[str | None] = []

            def state_path(_: dict[str, str], stem: str) -> Path:
                return fingerprint if stem == "embedding_fingerprint" else report

            def capture_write(path: Path, payload: dict) -> None:
                if path == fingerprint:
                    fingerprint_statuses.append(payload.get("status"))
                write_json_atomic(path, payload)

            processed = [{"file_path": str(prepared), "status": "processed"}]
            with (
                patch.object(ingest_script, "MANIFEST_PATH", manifest),
                patch.object(ingest_script, "workspace_state_path", side_effect=state_path),
                patch.object(
                    ingest_script,
                    "ensure_index_compatible",
                    return_value=current,
                ),
                patch.object(
                    ingest_script,
                    "ingest_path_for_record",
                    return_value=prepared,
                ),
                patch.object(ingest_script, "get_documents", return_value=processed),
                patch.object(ingest_script.httpx, "Client", _ReadOnlyClient),
                patch.object(
                    ingest_script,
                    "write_json_atomic",
                    side_effect=capture_write,
                ),
            ):
                ingest_script.main.__wrapped__(embedding_env())

            stored = json.loads(fingerprint.read_text(encoding="utf-8"))
            self.assertEqual(fingerprint_statuses, ["ready"])
            self.assertEqual(stored["status"], "ready")
            self.assertNotEqual(stored["recorded_at"], "2026-01-01T00:00:00+00:00")
            self.assertTrue(report.is_file())


if __name__ == "__main__":
    unittest.main()
