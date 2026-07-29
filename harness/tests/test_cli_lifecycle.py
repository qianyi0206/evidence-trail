from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from reg_harness import cli
from reg_harness.types import AgentState, EvidenceItem, ToolResult


class CliLifecycleTests(unittest.TestCase):
    @staticmethod
    def _stack_for_state(state: AgentState) -> MagicMock:
        stack = MagicMock()
        stack.chat = SimpleNamespace(on_token=None, stream_enabled=False)
        stack.ask.return_value = state
        return stack

    def test_no_live_stdout_is_one_complete_json_document(self) -> None:
        state = AgentState(question="适用于哪两类汽车？")
        state.evidence.append(
            EvidenceItem(
                kind="chunk",
                text="本文件适用于 M1 和 N1 类汽车。",
                evidence_ids=["gb39901:clause:1"],
            )
        )
        state.step = 2
        state.done = True
        state.phase = "done"
        state.final_answer = {
            "answerable": True,
            "answer": {"vehicle_categories": ["M1", "N1"]},
            "claims": ["本文件适用于 M1 和 N1 类汽车。"],
            "citations": ["E1"],
            "reason": "证据充分",
            "validation_flags": [],
        }
        stack = self._stack_for_state(state)
        stdout = io.StringIO()
        stderr = io.StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = cli._run_ask(stack, state.question, live=False)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(payload["question"], state.question)
        self.assertEqual(payload["final_answer"], state.final_answer)
        self.assertEqual(payload["evidence_count"], 1)
        self.assertNotIn("最终答案", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_no_live_valid_refusal_remains_successful_json(self) -> None:
        state = AgentState(question="证据中没有的问题")
        state.done = True
        state.phase = "done"
        state.refuse_reason = "证据不足"
        state.final_answer = {
            "answerable": False,
            "answer": {"answerable": False, "reason": "证据不足"},
            "claims": [],
            "citations": [],
            "reason": "证据不足",
            "validation_flags": [],
        }
        stack = self._stack_for_state(state)
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            result = cli._run_ask(stack, state.question, live=False)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertFalse(payload["final_answer"]["answerable"])
        self.assertEqual(payload["refuse_reason"], "证据不足")

    def test_main_no_live_uses_machine_readable_contract(self) -> None:
        state = AgentState(question="question", done=True, phase="done")
        state.final_answer = {
            "answerable": False,
            "answer": {"answerable": False, "reason": "insufficient evidence"},
            "claims": [],
            "citations": [],
            "reason": "insufficient evidence",
            "validation_flags": [],
        }
        stack = self._stack_for_state(state)
        stdout = io.StringIO()

        with (
            patch.object(cli, "build_stack", return_value=stack),
            redirect_stdout(stdout),
        ):
            result = cli.main(["ask", state.question, "--no-live"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(payload["final_answer"], state.final_answer)
        stack.close.assert_called_once()

    def test_no_live_dump_trace_keeps_stdout_clean(self) -> None:
        state = AgentState(question="question", done=True, phase="done")
        state.final_answer = {
            "answerable": False,
            "answer": {"answerable": False, "reason": "no evidence"},
            "claims": [],
            "citations": [],
            "reason": "no evidence",
            "validation_flags": [],
        }
        stack = self._stack_for_state(state)
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            trace_path = Path(tmp) / "trace.json"
            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = cli._run_ask(
                    stack,
                    state.question,
                    live=False,
                    dump_trace=str(trace_path),
                )
            dumped = json.loads(trace_path.read_text(encoding="utf-8"))

        payload = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(dumped, payload)
        self.assertIn("trace →", stderr.getvalue())

    def test_ask_closes_stack_when_run_fails(self) -> None:
        stack = MagicMock()
        args = SimpleNamespace(
            profile_env=None,
            question="question",
            policy="auto",
            max_steps=None,
            bootstrap=False,
            live=False,
            dump_trace=None,
        )
        with (
            patch.object(cli, "build_stack", return_value=stack),
            patch.object(cli, "_run_ask", side_effect=RuntimeError("ask failed")),
        ):
            with self.assertRaisesRegex(RuntimeError, "ask failed"):
                cli._cmd_ask(args)

        stack.close.assert_called_once()

    def test_chat_closes_stack_after_user_exits(self) -> None:
        stack = MagicMock()
        stack.describe.return_value = {}
        args = SimpleNamespace(
            profile_env=None,
            policy="auto",
            max_steps=None,
            bootstrap=False,
            dump_dir=None,
        )
        with (
            patch.object(cli, "build_stack", return_value=stack),
            patch("builtins.input", return_value="quit"),
            patch("builtins.print"),
        ):
            self.assertEqual(cli._cmd_chat(args), 0)

        stack.close.assert_called_once()

    def test_retrieve_closes_registry_and_rerank_when_run_fails(self) -> None:
        settings = SimpleNamespace()
        registry = MagicMock()
        registry.run.side_effect = RuntimeError("retrieve failed")
        args = SimpleNamespace(profile_env=None, question="question", mode="mix")
        with (
            patch.object(cli, "load_settings", return_value=settings),
            patch.object(cli, "default_registry", return_value=registry),
            patch.object(cli, "close_shared_rerank_client") as close_rerank,
        ):
            with self.assertRaisesRegex(RuntimeError, "retrieve failed"):
                cli._cmd_retrieve(args)

        registry.close.assert_called_once()
        close_rerank.assert_called_once_with(settings)

    def test_lookup_closes_registry_and_rerank_after_success(self) -> None:
        settings = SimpleNamespace(active_kb="test")
        registry = MagicMock()
        registry.run.return_value = ToolResult(
            name="clause_lookup",
            ok=True,
            content="found",
        )
        args = SimpleNamespace(
            profile_env=None,
            question="question",
            kind="clause",
            target="6.1",
            vehicle=None,
            ego_kmh=None,
            load_state=None,
            scenario=None,
        )
        with (
            patch.object(cli, "load_settings", return_value=settings),
            patch.object(cli, "default_registry", return_value=registry),
            patch.object(cli, "close_shared_rerank_client") as close_rerank,
            patch("builtins.print"),
        ):
            self.assertEqual(cli._cmd_lookup(args), 0)

        registry.close.assert_called_once()
        close_rerank.assert_called_once_with(settings)

    def test_describe_and_librarian_close_their_stacks(self) -> None:
        describe_stack = MagicMock()
        describe_stack.describe.return_value = {}
        with (
            patch.object(cli, "build_stack", return_value=describe_stack),
            patch("builtins.print"),
        ):
            self.assertEqual(
                cli._cmd_describe(SimpleNamespace(profile_env=None)),
                0,
            )
        describe_stack.close.assert_called_once()

        librarian_stack = MagicMock()
        with (
            patch.object(cli, "build_stack", return_value=librarian_stack),
            patch("builtins.print"),
        ):
            self.assertEqual(
                cli._cmd_librarian(SimpleNamespace(profile_env=None, action="unknown")),
                2,
            )
        librarian_stack.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
