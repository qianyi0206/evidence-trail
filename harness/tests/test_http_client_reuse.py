from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from reg_harness.config import Settings
from reg_harness.llm import ChatClient
from reg_harness.rerank import (
    close_shared_rerank_client,
    shared_rerank_client,
)
from reg_harness.runtime import HarnessStack
from reg_harness.tools.lightrag_retrieve import LightRAGRetrieveTool
from reg_harness.tools.registry import ToolRegistry, default_registry


def _settings() -> Settings:
    return Settings(
        aeb_root=Path(tempfile.gettempdir()),
        lightrag_url="http://127.0.0.1:9621",
        llm_host="https://llm.example/v1",
        llm_api_key="",
        llm_model="test-model",
        llm_extra_body=None,
    )


class HttpClientReuseTests(unittest.TestCase):
    def test_chat_client_reuses_and_closes_http_client(self) -> None:
        chat = ChatClient(_settings())
        with patch("reg_harness.llm.httpx.Client") as factory:
            first = chat._http_client()
            second = chat._http_client()
            self.assertIs(first, second)
            factory.assert_called_once()
            chat.close()
            factory.return_value.close.assert_called_once()

    def test_retrieve_tool_reuses_and_closes_http_client(self) -> None:
        tool = LightRAGRetrieveTool(
            _settings(),
            name="graph_search",
            default_mode="mix",
            description="test",
        )
        with patch("reg_harness.tools.lightrag_retrieve.httpx.Client") as factory:
            self.assertIs(tool._http_client(), tool._http_client())
            factory.assert_called_once()
            tool.close()
            factory.return_value.close.assert_called_once()

    def test_rerank_client_is_shared_per_stack_settings(self) -> None:
        owner = SimpleNamespace()
        fake = MagicMock()
        with patch("reg_harness.rerank.httpx.Client", return_value=fake) as factory:
            self.assertIs(
                shared_rerank_client(owner, timeout=30),
                shared_rerank_client(owner, timeout=30),
            )
            factory.assert_called_once()
            close_shared_rerank_client(owner)
            fake.close.assert_called_once()

    def test_default_registry_closes_only_the_chat_client_it_owns(self) -> None:
        owned_chat = MagicMock()
        with patch(
            "reg_harness.tools.registry.ChatClient", return_value=owned_chat
        ) as factory:
            registry = default_registry(_settings())
            registry.close()
            registry.close()

        factory.assert_called_once()
        owned_chat.close.assert_called_once()

        injected_chat = MagicMock()
        registry = default_registry(_settings(), chat=injected_chat)
        registry.close()
        injected_chat.close.assert_not_called()

    def test_registry_finishes_cleanup_before_reraising_first_error(self) -> None:
        first = SimpleNamespace(
            name="first",
            close=MagicMock(side_effect=RuntimeError("first-close-failed")),
        )
        second = SimpleNamespace(name="second", close=MagicMock())
        owned = SimpleNamespace(close=MagicMock())
        registry = ToolRegistry([first, second], owned_resources=[owned])

        with self.assertRaisesRegex(RuntimeError, "first-close-failed"):
            registry.close()

        second.close.assert_called_once()
        owned.close.assert_called_once()

    def test_stack_finishes_cleanup_before_reraising_first_error(self) -> None:
        stack = object.__new__(HarnessStack)
        stack.registry = MagicMock()
        stack.registry.close.side_effect = RuntimeError("registry-close-failed")
        stack.chat = MagicMock()
        stack.settings = SimpleNamespace()

        with patch("reg_harness.rerank.close_shared_rerank_client") as close_rerank:
            with self.assertRaisesRegex(RuntimeError, "registry-close-failed"):
                stack.close()

        stack.chat.close.assert_called_once()
        close_rerank.assert_called_once_with(stack.settings)


if __name__ == "__main__":
    unittest.main()
