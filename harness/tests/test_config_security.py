from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from reg_harness.config import load_settings
from probe_models import validate_rerank_config


class ConfigSecurityTests(unittest.TestCase):
    def test_rerank_does_not_reuse_unrelated_llm_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text(
                "\n".join(
                    [
                        "LLM_BINDING_API_KEY=llm-provider-secret",
                        "RERANK_BINDING=aliyun",
                        "RERANK_MODEL=qwen3-rerank",
                        "RERANK_BINDING_HOST=https://dashscope.aliyuncs.com/rerank",
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                settings = load_settings(aeb_root=root)
        self.assertEqual(settings.rerank_api_key, "")
        self.assertFalse(settings.bag_rerank_enabled)

    def test_dashscope_key_is_accepted_for_dashscope_rerank(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text(
                "\n".join(
                    [
                        "LLM_BINDING_API_KEY=llm-provider-secret",
                        "DASHSCOPE_API_KEY=dashscope-secret",
                        "RERANK_BINDING=aliyun",
                        "RERANK_MODEL=qwen3-rerank",
                        "RERANK_BINDING_HOST=https://dashscope.aliyuncs.com/rerank",
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                settings = load_settings(aeb_root=root)
        self.assertEqual(settings.rerank_api_key, "dashscope-secret")
        self.assertTrue(settings.bag_rerank_enabled)

    def test_explicit_missing_profile_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "Profile env file does not exist"):
                    load_settings(profile_env=".env.missing", aeb_root=root)

    def test_profile_must_stay_below_aeb_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "aeb"
            root.mkdir()
            outside = Path(tmp) / ".env.outside"
            outside.write_text("WORKSPACE=outside\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "must stay inside"):
                    load_settings(profile_env=str(outside), aeb_root=root)

    def test_root_relative_profile_remains_supported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.profile").write_text(
                "WORKSPACE=aeb_gb39901_v4_relation_guard\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                settings = load_settings(profile_env=".env.profile", aeb_root=root)
        self.assertEqual(settings.workspace, "aeb_gb39901_v4_relation_guard")

    def test_enabled_rerank_requires_an_independent_key(self) -> None:
        env = {
            "LLM_BINDING_API_KEY": "llm-provider-secret",
            "RERANK_BINDING": "aliyun",
            "RERANK_MODEL": "qwen3-rerank",
            "RERANK_BINDING_HOST": "https://dashscope.aliyuncs.com/rerank",
        }
        with self.assertRaisesRegex(RuntimeError, "independent"):
            validate_rerank_config(env)

    def test_enabled_rerank_accepts_explicit_key(self) -> None:
        env = {
            "LLM_BINDING_API_KEY": "llm-provider-secret",
            "RERANK_BINDING": "aliyun",
            "RERANK_MODEL": "qwen3-rerank",
            "RERANK_BINDING_HOST": "https://dashscope.aliyuncs.com/rerank",
            "RERANK_BINDING_API_KEY": "rerank-provider-secret",
        }
        validate_rerank_config(env)


if __name__ == "__main__":
    unittest.main()
