from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from apps.gradio_pipeline import (
    MAX_QUESTION_CHARS,
    DemoApp,
    _launch_auth,
    _launch_with_cleanup,
    build_ui,
)


class _FailingStack:
    def ask(self, *_args, **_kwargs):
        raise RuntimeError("secret-backend-detail")


class _CountingStack:
    def __init__(self) -> None:
        self.calls = 0

    def ask(self, *_args, **_kwargs):
        self.calls += 1
        raise AssertionError("model call must not run")


class GradioSecurityTests(unittest.TestCase):
    def test_share_requires_auth(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "--share requires"):
                _launch_auth(
                    share=True,
                    username="",
                    password_env="GRADIO_AUTH_PASSWORD",
                )

    def test_share_reads_password_from_environment(self) -> None:
        with patch.dict(
            os.environ,
            {"GRADIO_AUTH_PASSWORD": "strong-test-password"},
            clear=True,
        ):
            self.assertEqual(
                _launch_auth(
                    share=True,
                    username="reviewer",
                    password_env="GRADIO_AUTH_PASSWORD",
                ),
                ("reviewer", "strong-test-password"),
            )

    def test_build_ui_rejects_public_share_without_auth(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires non-empty authentication"):
            build_ui(
                ".env.gb39901_v4",
                share=True,
                server_port=7860,
                auth=None,
            )

    def test_public_errors_do_not_expose_backend_detail(self) -> None:
        app = DemoApp(".env.gb39901_v4", expose_errors=False)
        app._stack = _FailingStack()
        app._last_profile = app.profile_env

        rendered = app.run("AEB 要求是什么？", 6)

        self.assertNotIn("secret-backend-detail", rendered[0])
        self.assertNotIn("secret-backend-detail", rendered[4])
        self.assertIn("request_failed", rendered[4])

    def test_long_question_is_rejected_before_model_call(self) -> None:
        app = DemoApp(".env.gb39901_v4")
        app._stack = _FailingStack()
        app._last_profile = app.profile_env

        rendered = app.run("问" * (MAX_QUESTION_CHARS + 1), 6)

        self.assertIn("问题过长", rendered[0])
        self.assertIn("question_too_long", rendered[4])

    def test_max_steps_is_bounded_before_model_call(self) -> None:
        app = DemoApp(".env.gb39901_v4")
        stack = _CountingStack()
        app._stack = stack
        app._last_profile = app.profile_env

        rendered = app.run("AEB 要求是什么？", 1_000_000)

        self.assertEqual(stack.calls, 0)
        self.assertIn("max_steps", rendered[0])
        self.assertIn("invalid_max_steps", rendered[4])

    def test_demo_close_releases_stack_once(self) -> None:
        app = DemoApp(".env.gb39901_v4")
        stack = MagicMock()
        app._stack = stack
        app._last_profile = app.profile_env

        app.close()
        app.close()

        stack.close.assert_called_once()
        self.assertIsNone(app._stack)
        self.assertIsNone(app._last_profile)

    def test_launch_cleanup_runs_after_normal_shutdown(self) -> None:
        gradio_app = MagicMock()
        demo = MagicMock()

        _launch_with_cleanup(gradio_app, demo, server_name="127.0.0.1")

        gradio_app.launch.assert_called_once_with(server_name="127.0.0.1")
        demo.close.assert_called_once()

    def test_launch_cleanup_runs_when_launch_fails(self) -> None:
        gradio_app = MagicMock()
        gradio_app.launch.side_effect = RuntimeError("bind failed")
        demo = MagicMock()

        with self.assertRaisesRegex(RuntimeError, "bind failed"):
            _launch_with_cleanup(gradio_app, demo)

        demo.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
