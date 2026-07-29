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
    @staticmethod
    def _load_with_environment(values: dict[str, str]):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict(os.environ, values, clear=True):
                return load_settings(aeb_root=root)

    def test_invalid_openai_extra_body_fails_fast(self) -> None:
        for value, expected in (
            ("{not-json", "valid JSON"),
            ('["not", "an", "object"]', "JSON object"),
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    RuntimeError,
                    rf"OPENAI_LLM_EXTRA_BODY.*{expected}",
                ):
                    self._load_with_environment({"OPENAI_LLM_EXTRA_BODY": value})

    def test_invalid_catalog_and_graph_modes_fail_fast(self) -> None:
        for name, value in (
            ("HARNESS_CATALOG_MODE", "typo"),
            ("HARNESS_GRAPH_DEFAULT_MODE", "unknown"),
        ):
            with self.subTest(name=name):
                with self.assertRaisesRegex(RuntimeError, name):
                    self._load_with_environment({name: value})

    def test_invalid_boolean_flag_fails_fast(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "HARNESS_ENABLE_RERANK"):
            self._load_with_environment({"HARNESS_ENABLE_RERANK": "treu"})

    def test_critical_numeric_settings_fail_fast(self) -> None:
        invalid_values = (
            ("HARNESS_TEMPERATURE", "-0.1"),
            ("HARNESS_TIMEOUT", "0"),
            ("HARNESS_TIMEOUT", "nan"),
            ("HARNESS_MAX_STEPS", "0"),
            ("HARNESS_TOP_K", "101"),
            ("HARNESS_TOP_K", "many"),
            ("HARNESS_CONTEXT_TOKENS", "255"),
            ("MIN_RERANK_SCORE", "1.1"),
            ("HARNESS_CHUNK_BACKFILL_MAX", "0"),
            ("HARNESS_CHUNK_BACKFILL_MIN_COOCCUR", "0"),
            ("HARNESS_BAG_LIMIT", "0"),
            ("HARNESS_BAG_MAX_ENTITIES", "0"),
            ("HARNESS_BAG_MAX_RELATIONS", "101"),
            ("HARNESS_ENTITY_TOKEN_FRACTION", "0.09"),
            ("HARNESS_RELATION_TOKEN_FRACTION", "0.41"),
        )
        for name, value in invalid_values:
            with self.subTest(name=name, value=value):
                with self.assertRaisesRegex(RuntimeError, name):
                    self._load_with_environment({name: value})

    def test_combined_graph_token_fraction_fails_fast(self) -> None:
        values = {
            "HARNESS_ENTITY_TOKEN_FRACTION": "0.4",
            "HARNESS_RELATION_TOKEN_FRACTION": "0.4",
        }
        with self.assertRaisesRegex(
            RuntimeError,
            "HARNESS_ENTITY_TOKEN_FRACTION.*HARNESS_RELATION_TOKEN_FRACTION",
        ):
            self._load_with_environment(values)

    def test_valid_numeric_settings_are_preserved(self) -> None:
        settings = self._load_with_environment(
            {
                "HARNESS_TEMPERATURE": "0.5",
                "HARNESS_TIMEOUT": "30",
                "HARNESS_MAX_STEPS": "8",
                "HARNESS_TOP_K": "50",
                "HARNESS_CONTEXT_TOKENS": "24000",
                "MIN_RERANK_SCORE": "0.25",
                "HARNESS_CHUNK_BACKFILL_MAX": "12",
                "HARNESS_CHUNK_BACKFILL_MIN_COOCCUR": "2",
                "HARNESS_BAG_LIMIT": "40",
                "HARNESS_BAG_MAX_ENTITIES": "6",
                "HARNESS_BAG_MAX_RELATIONS": "7",
                "HARNESS_ENTITY_TOKEN_FRACTION": "0.2",
                "HARNESS_RELATION_TOKEN_FRACTION": "0.3",
            }
        )
        self.assertEqual(settings.temperature, 0.5)
        self.assertEqual(settings.request_timeout, 30.0)
        self.assertEqual(settings.default_max_steps, 8)
        self.assertEqual(settings.retrieve_top_k, 50)
        self.assertEqual(settings.context_tokens, 24000)
        self.assertEqual(settings.min_rerank_score, 0.25)
        self.assertEqual(settings.chunk_backfill_max, 12)
        self.assertEqual(settings.chunk_backfill_min_cooccur, 2)
        self.assertEqual(settings.bag_limit, 40)
        self.assertEqual(settings.bag_max_entities, 6)
        self.assertEqual(settings.bag_max_relations, 7)
        self.assertEqual(settings.entity_token_fraction, 0.2)
        self.assertEqual(settings.relation_token_fraction, 0.3)

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
