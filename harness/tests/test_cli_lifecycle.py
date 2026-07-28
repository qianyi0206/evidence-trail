from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from reg_harness import cli
from reg_harness.types import ToolResult


class CliLifecycleTests(unittest.TestCase):
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
