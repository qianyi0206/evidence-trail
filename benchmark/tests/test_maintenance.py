from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "benchmark" / "scripts"))

import check_snapshot_compat  # noqa: E402
from generate_report import (  # noqa: E402
    available_labeled_paths,
    require_comparable_labeled_scores,
    require_matching_labeled_runs,
)


class SnapshotCompatibilityTest(unittest.TestCase):
    def _root(self, temp_dir: str, *, model: str = "embed-v1") -> Path:
        root = Path(temp_dir)
        (root / "state").mkdir()
        (root / ".env").write_text(
            "\n".join(
                [
                    f"EMBEDDING_MODEL={model}",
                    "EMBEDDING_DIM=2560",
                    "EMBEDDING_TOKEN_LIMIT=128000",
                    "EMBEDDING_BINDING_API_KEY=must-not-be-printed",
                ]
            ),
            encoding="utf-8",
        )
        (root / ".env.profile").write_text("WORKSPACE=demo_v4\n", encoding="utf-8")
        (root / "state" / "embedding_fingerprint.demo_v4.json").write_text(
            json.dumps(
                {
                    "status": "ready",
                    "config": {
                        "model": "embed-v1",
                        "dimension": 2560,
                        "token_limit": 128000,
                    },
                }
            ),
            encoding="utf-8",
        )
        return root

    def test_matching_snapshot_prints_only_non_secret_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._root(temp_dir)
            output = io.StringIO()
            with redirect_stdout(output):
                result = check_snapshot_compat.main(
                    ["--profile-env", ".env.profile"],
                    root=root,
                )
        rendered = output.getvalue()
        self.assertEqual(result, 0)
        self.assertIn("expected='embed-v1' actual='embed-v1' [OK]", rendered)
        self.assertIn("snapshot   OK", rendered)
        self.assertNotIn("must-not-be-printed", rendered)
        self.assertNotIn("API_KEY", rendered)

    def test_mismatch_fails_before_external_probes_with_expected_and_actual(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._root(temp_dir, model="embed-v2")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = check_snapshot_compat.main(
                    ["--profile-env", ".env.profile"],
                    root=root,
                )
        self.assertEqual(result, 1)
        self.assertIn("expected='embed-v1' actual='embed-v2' [MISMATCH]", stdout.getvalue())
        self.assertIn("snapshot   FAILED", stderr.getvalue())

    def test_missing_fingerprint_is_rebuild_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._root(temp_dir)
            (root / "state" / "embedding_fingerprint.demo_v4.json").unlink()
            output = io.StringIO()
            with redirect_stdout(output):
                result = check_snapshot_compat.main(
                    ["--profile-env", ".env.profile"],
                    root=root,
                )
        self.assertEqual(result, 0)
        self.assertIn("SKIPPED", output.getvalue())
        self.assertIn("rebuild path", output.getvalue())

    def test_missing_fingerprint_rejects_nonempty_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._root(temp_dir)
            (root / "state" / "embedding_fingerprint.demo_v4.json").unlink()
            workspace = root / "data" / "rag_storage" / "demo_v4"
            workspace.mkdir(parents=True)
            (workspace / "vdb_entities.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(
                RuntimeError,
                "Missing snapshot fingerprint for non-empty workspace",
            ):
                check_snapshot_compat.main(
                    ["--profile-env", ".env.profile"],
                    root=root,
                )


class ReportInputTest(unittest.TestCase):
    @staticmethod
    def _score(
        *,
        fingerprint: str,
        question_ids: list[str] | None = None,
        workspace: str = "workspace-a",
    ) -> dict:
        return {
            "run_manifest": {
                "fingerprint": fingerprint,
                "runner": "run_graphrag_benchmark",
                "selected_question_ids": question_ids or ["q1", "q2"],
                "modes": ["closed_book", "naive", "mix"],
                "configuration": {
                    "profile_env": f".env.{workspace}",
                    "profile_sha256": f"profile-{workspace}",
                    "resolved_workspace": workspace,
                    "index_identity": {"workspace": workspace},
                    "source_set": "gb",
                    "split": "all",
                    "context_tokens": 6000,
                    "top_k": 20,
                    "context_policy": "shared_budget",
                    "retrieval_only": False,
                    "llm_model": "answer-model",
                },
                "code": [{"path": "runner.py", "sha256": "same-code"}],
            },
            "scoring_config": {
                "bootstrap_samples": 2000,
                "seed": 39901,
                "paired_baseline": "naive",
            },
        }

    def test_available_labeled_paths_keeps_current_files_and_lists_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            current = root / "current.json"
            current.write_text("{}", encoding="utf-8")
            available, missing = available_labeled_paths(
                [("A0", current), ("A3-v4", root / "missing.json")]
            )
        self.assertEqual(available, [("A0", current)])
        self.assertEqual(missing, [("A3-v4", root / "missing.json")])

    def test_variant_workspace_identity_does_not_block_comparison(self) -> None:
        require_comparable_labeled_scores(
            [
                ("A0", self._score(fingerprint="run-a", workspace="a0")),
                ("A3-v4", self._score(fingerprint="run-b", workspace="v4")),
            ],
            score_kind="retrieval",
        )

    def test_different_question_sets_cannot_share_a_comparison_table(self) -> None:
        with self.assertRaisesRegex(
            SystemExit,
            "not comparable.*selected_question_ids",
        ):
            require_comparable_labeled_scores(
                [
                    ("A0", self._score(fingerprint="run-a")),
                    (
                        "A3-v4",
                        self._score(
                            fingerprint="run-b",
                            question_ids=["q1"],
                            workspace="v4",
                        ),
                    ),
                ],
                score_kind="retrieval",
            )

    def test_retrieval_and_answer_scores_must_come_from_same_run(self) -> None:
        with self.assertRaisesRegex(SystemExit, "come from different runs"):
            require_matching_labeled_runs(
                [("A3-v4", self._score(fingerprint="retrieval-run"))],
                [("A3-v4", self._score(fingerprint="answer-run"))],
            )


if __name__ == "__main__":
    unittest.main()
