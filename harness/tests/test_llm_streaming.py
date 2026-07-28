from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reg_harness.config import Settings
from reg_harness.llm import ChatClient, StreamUnsupportedError


def client() -> ChatClient:
    settings = Settings(
        aeb_root=Path(tempfile.gettempdir()),
        lightrag_url="http://127.0.0.1:9621",
        llm_host="https://llm.example/v1",
        llm_api_key="",
        llm_model="test-model",
        llm_extra_body=None,
    )
    return ChatClient(settings)


class LlmStreamingTests(unittest.TestCase):
    def test_explicit_stream_rejection_falls_back_once(self) -> None:
        chat = client()
        expected = {"action": "final"}
        with (
            patch.object(
                chat,
                "_complete_json_stream",
                side_effect=StreamUnsupportedError("unsupported"),
            ) as stream_call,
            patch.object(
                chat,
                "_complete_json_blocking",
                return_value=expected,
            ) as blocking_call,
        ):
            actual = chat.complete_json("system", "user", on_token=lambda _: None)
        self.assertEqual(actual, expected)
        stream_call.assert_called_once()
        blocking_call.assert_called_once()

    def test_interrupted_stream_is_not_retried(self) -> None:
        chat = client()
        with (
            patch.object(
                chat,
                "_complete_json_stream",
                side_effect=TimeoutError("stream interrupted"),
            ),
            patch.object(chat, "_complete_json_blocking") as blocking_call,
        ):
            with self.assertRaisesRegex(TimeoutError, "interrupted"):
                chat.complete_json("system", "user", on_token=lambda _: None)
        blocking_call.assert_not_called()

    def test_invalid_stream_json_is_not_retried(self) -> None:
        chat = client()
        with (
            patch.object(
                chat,
                "_complete_json_stream",
                side_effect=ValueError("invalid JSON"),
            ),
            patch.object(chat, "_complete_json_blocking") as blocking_call,
        ):
            with self.assertRaisesRegex(ValueError, "invalid JSON"):
                chat.complete_json("system", "user", on_token=lambda _: None)
        blocking_call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
