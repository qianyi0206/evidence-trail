from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from apps.gradio_pipeline import _format_evidence
from reg_harness.config import Settings
from reg_harness.guards import validate_final_answer
from reg_harness.loop import _bag_signature, state_to_dict
from reg_harness.tools.base import Tool
from reg_harness.tools.compose_answer import ComposeAnswerTool
from reg_harness.tools.finalize import FinalizeTool
from reg_harness.tools.lightrag_retrieve import (
    LightRAGRetrieveTool,
    backfill_chunks_from_graph_hits,
)
from reg_harness.tools.registry import ToolRegistry
from reg_harness.types import AgentState, EvidenceItem, ToolResult


def _settings(root: Path = Path("."), workspace: str = "test") -> Settings:
    return Settings(
        aeb_root=root,
        lightrag_url="http://127.0.0.1:9621",
        llm_host="",
        llm_api_key="",
        llm_model="test",
        llm_extra_body=None,
        workspace=workspace,
        active_kb="gb39901",
    )


class StableEvidenceLabelTests(unittest.TestCase):
    def test_compose_reorders_presentation_but_preserves_bag_labels(self) -> None:
        state = AgentState(
            question="q",
            evidence=[
                EvidenceItem(kind="entity", text="实体摘要"),
                EvidenceItem(kind="relationship", text="关系摘要"),
                EvidenceItem(kind="chunk", text="最大速度为 60 km/h。"),
            ],
        )
        render = state.render_evidence(for_compose=True)
        self.assertLess(render.text.index("[E3]"), render.text.index("[E2]"))
        self.assertLess(render.text.index("[E2]"), render.text.index("[E1]"))
        self.assertIs(render.by_label()["E3"], state.evidence[2])

        checked = validate_final_answer(
            state,
            {
                "answerable": True,
                "answer": {"maximum_speed": "60 km/h"},
                "claims": ["最大速度为 60 km/h"],
                "citations": ["E3"],
            },
        )
        self.assertTrue(checked["answerable"])

    def test_label_omitted_by_prompt_budget_cannot_be_cited(self) -> None:
        state = AgentState(
            question="q",
            evidence=[
                EvidenceItem(
                    kind="chunk",
                    text=(f"证据 {index} 最大速度为 {index} km/h。" + "长文本" * 3000),
                )
                for index in range(1, 21)
            ],
        )
        render = state.render_evidence(for_compose=True)
        self.assertNotIn("E20", render.labels)
        checked = validate_final_answer(
            state,
            {
                "answerable": True,
                "answer": {"maximum_speed": "20 km/h"},
                "claims": ["最大速度为 20 km/h"],
                "citations": ["E20"],
            },
        )
        self.assertFalse(checked["answerable"])
        self.assertIn(
            "forced_refusal_invalid_citations", checked["validation_flags"]
        )

    def test_ui_uses_same_compose_labels(self) -> None:
        state = AgentState(
            question="q",
            evidence=[
                EvidenceItem(kind="entity", text="实体"),
                EvidenceItem(kind="chunk", text="原文"),
            ],
        )
        ui = _format_evidence(state)
        self.assertLess(ui.index("[E2]"), ui.index("[E1]"))


class ClaimGroundingTests(unittest.TestCase):
    def _prediction(self, claim: str, answer: dict[str, Any]) -> dict[str, Any]:
        return {
            "answerable": True,
            "answer": answer,
            "claims": [claim],
            "citations": ["E1"],
        }

    def test_small_decimal_is_not_treated_as_enumeration(self) -> None:
        state = AgentState(
            question="TTC",
            evidence=[EvidenceItem(kind="chunk", text="试验速度为 60 km/h。")],
        )
        checked = validate_final_answer(
            state,
            self._prediction("TTC 阈值为 4.9 s", {"ttc": "4.9 s"}),
        )
        self.assertFalse(checked["answerable"])
        self.assertIn(
            "forced_refusal_ungrounded_numeric", checked["validation_flags"]
        )

    def test_dimensional_answer_requires_its_unit(self) -> None:
        state = AgentState(
            question="q",
            evidence=[EvidenceItem(kind="chunk", text="试验速度为 60 km/h。")],
        )
        checked = validate_final_answer(
            state,
            self._prediction("试验速度为 60", {"speed": 60}),
        )
        self.assertFalse(checked["answerable"])
        self.assertIn(
            "forced_refusal_ungrounded_numeric", checked["validation_flags"]
        )

    def test_clause_identifier_is_not_mistaken_for_unitless_speed(self) -> None:
        state = AgentState(
            question="q",
            evidence=[
                EvidenceItem(
                    kind="chunk",
                    text="6.11 规定误响应试验，速度要求另见对应场景。",
                )
            ],
        )
        checked = validate_final_answer(
            state,
            self._prediction(
                "6.11 规定误响应试验",
                {"clause": "6.11", "topic": "误响应试验"},
            ),
        )
        self.assertTrue(checked["answerable"])

    def test_number_must_match_unit_and_condition_in_citation(self) -> None:
        state = AgentState(
            question="q",
            evidence=[
                EvidenceItem(
                    kind="chunk",
                    text="M1 类车辆以 60 km/h 接近静止车辆目标。",
                )
            ],
        )
        wrong_unit = validate_final_answer(
            state,
            self._prediction("TTC 为 60 s", {"ttc": "60 s"}),
        )
        wrong_vehicle = validate_final_answer(
            state,
            self._prediction(
                "N1 类车辆速度为 60 km/h",
                {"vehicle": "N1", "speed": "60 km/h"},
            ),
        )
        self.assertIn(
            "forced_refusal_ungrounded_numeric", wrong_unit["validation_flags"]
        )
        self.assertIn(
            "forced_refusal_ungrounded_numeric", wrong_vehicle["validation_flags"]
        )

    def test_table_value_must_match_conditions_on_the_same_row(self) -> None:
        state = AgentState(
            question="q",
            evidence=[
                EvidenceItem(
                    kind="chunk",
                    text=(
                        "M1 类车辆速度 60 km/h，最大相对碰撞速度为 5 km/h；"
                        "N1 类车辆速度 60 km/h，最大相对碰撞速度为 10 km/h。"
                    ),
                )
            ],
        )
        checked = validate_final_answer(
            state,
            self._prediction(
                "M1 类车辆速度 60 km/h 时，最大相对碰撞速度为 10 km/h",
                {
                    "vehicle": "M1",
                    "ego_speed": "60 km/h",
                    "maximum_relative_collision_speed": "10 km/h",
                },
            ),
        )
        self.assertFalse(checked["answerable"])
        self.assertIn(
            "forced_refusal_ungrounded_numeric", checked["validation_flags"]
        )

    def test_qualitative_negation_must_match_cited_text(self) -> None:
        state = AgentState(
            question="q",
            evidence=[EvidenceItem(kind="chunk", text="系统应发出碰撞预警。")],
        )
        checked = validate_final_answer(
            state,
            self._prediction(
                "系统不应发出碰撞预警",
                {"conclusion": "系统不应发出碰撞预警"},
            ),
        )
        self.assertFalse(checked["answerable"])
        self.assertIn(
            "forced_refusal_ungrounded_claims", checked["validation_flags"]
        )

    def test_same_polarity_but_different_predicate_is_not_grounded(self) -> None:
        state = AgentState(
            question="q",
            evidence=[
                EvidenceItem(kind="chunk", text="系统不应触发自动紧急制动。")
            ],
        )
        checked = validate_final_answer(
            state,
            self._prediction(
                "系统不应发出碰撞预警",
                {"conclusion": "系统不应发出碰撞预警"},
            ),
        )
        self.assertFalse(checked["answerable"])
        self.assertIn(
            "forced_refusal_ungrounded_claims", checked["validation_flags"]
        )

    def test_multiple_answer_numbers_keep_their_own_context(self) -> None:
        state = AgentState(
            question="q",
            evidence=[
                EvidenceItem(
                    kind="chunk",
                    text="M1 类车辆速度为 60 km/h，TTC 阈值为 4 s。",
                )
            ],
        )
        checked = validate_final_answer(
            state,
            {
                "answerable": True,
                "answer": {
                    "vehicle": "M1",
                    "speed": "60 km/h",
                    "ttc": "4 s",
                },
                "claims": ["M1 类车辆速度为 60 km/h", "TTC 阈值为 4 s"],
                "citations": ["E1"],
            },
        )
        self.assertTrue(checked["answerable"])

    def test_visible_list_number_is_allowed_as_enumeration(self) -> None:
        state = AgentState(
            question="q",
            evidence=[EvidenceItem(kind="chunk", text="自动紧急制动不应触发。")],
        )
        checked = validate_final_answer(
            state,
            self._prediction(
                "1. 自动紧急制动不应触发",
                {"items": ["1. 自动紧急制动不应触发"]},
            ),
        )
        self.assertTrue(checked["answerable"])


class FinalAnswerContractTests(unittest.TestCase):
    def test_finalize_rejects_missing_answerable_without_ending(self) -> None:
        state = AgentState(question="q")
        result = FinalizeTool().run(state, {})
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "invalid_final_contract")
        self.assertFalse(state.done)

    def test_finalize_accepts_explicit_well_formed_refusal(self) -> None:
        state = AgentState(question="q")
        result = FinalizeTool().run(
            state,
            {"answerable": False, "reason": "关键条款未检索到"},
        )
        self.assertTrue(result.ok)
        self.assertTrue(state.done)
        self.assertFalse(state.final_answer["answerable"])
        self.assertEqual(state.final_answer["claims"], [])
        self.assertEqual(state.final_answer["citations"], [])

    def test_finalize_rejects_malformed_refusal(self) -> None:
        state = AgentState(question="q")
        result = FinalizeTool().run(
            state,
            {
                "answerable": False,
                "reason": "证据不足",
                "claims": ["仍然输出声明"],
            },
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "guard_failed")
        self.assertFalse(state.done)

    def test_accept_draft_runs_same_grounding_guards(self) -> None:
        state = AgentState(
            question="q",
            evidence=[EvidenceItem(kind="chunk", text="系统不应触发紧急制动。")],
            draft_answer={
                "answerable": True,
                "answer": {"conclusion": "系统不应触发紧急制动"},
                "claims": ["系统不应触发紧急制动"],
                "citations": ["E1"],
            },
        )
        result = FinalizeTool().run(state, {"accept_draft": True})
        self.assertTrue(result.ok)
        self.assertTrue(state.done)


class RegistryValidationTests(unittest.TestCase):
    def test_retrieve_schema_rejects_wrong_type_and_range_before_network(self) -> None:
        tool = LightRAGRetrieveTool(
            _settings(), "vector_search", "naive", "retrieve"
        )
        registry = ToolRegistry([tool])
        state = AgentState(question="q")
        wrong_type = registry.run(
            "vector_search", state, {"query": "q", "top_k": "many"}
        )
        too_large = registry.run(
            "vector_search", state, {"query": "q", "top_k": 101}
        )
        self.assertEqual(wrong_type.error, "invalid_tool_arguments")
        self.assertEqual(too_large.error, "invalid_tool_arguments")
        self.assertEqual(state.recent_calls, [])

    def test_tool_exception_is_isolated(self) -> None:
        class ExplodingTool(Tool):
            name = "explode"
            description = "test"
            parameters = {
                "type": "object",
                "additionalProperties": False,
                "properties": {},
            }

            def run(self, state: AgentState, args: dict[str, Any]) -> ToolResult:
                raise ValueError("sensitive backend detail")

        result = ToolRegistry([ExplodingTool()]).run(
            "explode", AgentState(question="q"), {}
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "tool_exception")
        self.assertNotIn("sensitive backend detail", result.content)

    def test_non_object_argument_payload_is_rejected(self) -> None:
        tool = LightRAGRetrieveTool(
            _settings(), "vector_search", "naive", "retrieve"
        )
        result = ToolRegistry([tool]).run(
            "vector_search",
            AgentState(question="q"),
            ["query", "q"],  # type: ignore[arg-type]
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "invalid_tool_arguments")

    def test_legitimate_schema_input_still_reaches_tool(self) -> None:
        class EchoTool(Tool):
            name = "echo"
            description = "test"
            parameters = {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "count": {"type": "integer", "minimum": 1, "maximum": 3}
                },
                "required": ["count"],
            }

            def run(self, state: AgentState, args: dict[str, Any]) -> ToolResult:
                return ToolResult(name=self.name, ok=True, content=str(args["count"]))

        result = ToolRegistry([EchoTool()]).run(
            "echo", AgentState(question="q"), {"count": 2}
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.content, "2")


class LightRAGResponseAndCacheTests(unittest.TestCase):
    def test_non_object_lightrag_json_is_rejected(self) -> None:
        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> list[str]:
                return ["not", "an", "object"]

        class FakeClient:
            def __init__(self, **kwargs: Any):
                pass

            def __enter__(self) -> FakeClient:
                return self

            def __exit__(self, *args: Any) -> None:
                return None

            def post(self, *args: Any, **kwargs: Any) -> FakeResponse:
                return FakeResponse()

        tool = LightRAGRetrieveTool(
            _settings(), "vector_search", "naive", "retrieve"
        )
        with patch(
            "reg_harness.tools.lightrag_retrieve.httpx.Client", FakeClient
        ):
            result = tool.run(AgentState(question="q"), {"query": "q"})
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "invalid_lightrag_response")

    def test_malformed_lightrag_bucket_is_rejected(self) -> None:
        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, Any]:
                return {
                    "status": "success",
                    "data": {"chunks": "not-an-array"},
                }

        class FakeClient:
            def __init__(self, **kwargs: Any):
                pass

            def __enter__(self) -> FakeClient:
                return self

            def __exit__(self, *args: Any) -> None:
                return None

            def post(self, *args: Any, **kwargs: Any) -> FakeResponse:
                return FakeResponse()

        tool = LightRAGRetrieveTool(
            _settings(), "vector_search", "naive", "retrieve"
        )
        with patch(
            "reg_harness.tools.lightrag_retrieve.httpx.Client", FakeClient
        ):
            result = tool.run(AgentState(question="q"), {"query": "q"})
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "invalid_lightrag_response")
        self.assertEqual(result.data["malformed_fields"], ["chunks"])

    def test_chunk_cache_refreshes_when_store_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = "ws"
            store_dir = root / "data" / "rag_storage" / workspace
            store_dir.mkdir(parents=True)
            store_path = store_dir / "kv_store_text_chunks.json"
            chunk_id = "chunk-1"
            store_path.write_text(
                json.dumps({chunk_id: {"content": "版本A", "file_path": "a.md"}}),
                encoding="utf-8",
            )
            settings = _settings(root, workspace)
            settings._resolved_workspace = workspace  # type: ignore[attr-defined]
            items = [
                EvidenceItem(
                    kind="relationship",
                    text="edge",
                    raw={"source_id": chunk_id},
                )
            ]
            first = backfill_chunks_from_graph_hits(settings, items)
            old_stat = store_path.stat()
            store_path.write_text(
                json.dumps({chunk_id: {"content": "版本B", "file_path": "b.md"}}),
                encoding="utf-8",
            )
            os.utime(
                store_path,
                ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns + 1_000_000),
            )
            second = backfill_chunks_from_graph_hits(settings, items)
            self.assertEqual(first[0].text, "版本A")
            self.assertEqual(second[0].text, "版本B")

    def test_empty_cache_detects_store_created_later(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = "ws"
            settings = _settings(root, workspace)
            settings._resolved_workspace = workspace  # type: ignore[attr-defined]
            items = [
                EvidenceItem(
                    kind="relationship",
                    text="edge",
                    raw={"source_id": "chunk-1"},
                )
            ]
            self.assertEqual(backfill_chunks_from_graph_hits(settings, items), [])
            store_dir = root / "data" / "rag_storage" / workspace
            store_dir.mkdir(parents=True)
            (store_dir / "kv_store_text_chunks.json").write_text(
                json.dumps(
                    {"chunk-1": {"content": "后来创建", "file_path": "a.md"}}
                ),
                encoding="utf-8",
            )
            refreshed = backfill_chunks_from_graph_hits(settings, items)
            self.assertEqual(refreshed[0].text, "后来创建")


class StagnationFingerprintTests(unittest.TestCase):
    def test_same_count_with_changed_text_is_not_stagnant(self) -> None:
        before = [EvidenceItem(kind="chunk", text="旧正文", evidence_ids=["id-1"])]
        after = [EvidenceItem(kind="chunk", text="新正文", evidence_ids=["id-1"])]
        self.assertNotEqual(_bag_signature(before), _bag_signature(after))

    def test_same_text_with_changed_evidence_id_is_not_stagnant(self) -> None:
        before = [EvidenceItem(kind="chunk", text="正文", evidence_ids=["id-1"])]
        after = [EvidenceItem(kind="chunk", text="正文", evidence_ids=["id-2"])]
        self.assertNotEqual(_bag_signature(before), _bag_signature(after))


class ComposeTraceMappingTests(unittest.TestCase):
    def test_trace_records_exact_label_map(self) -> None:
        class FakeChat:
            def complete_json(self, system: str, user: str) -> dict[str, Any]:
                return {
                    "answerable": True,
                    "answer": {"maximum_speed": "60 km/h"},
                    "claims": ["最大速度为 60 km/h"],
                    "citations": ["E2"],
                }

        state = AgentState(
            question="q",
            evidence=[
                EvidenceItem(kind="entity", text="实体"),
                EvidenceItem(
                    kind="chunk",
                    text="最大速度为 60 km/h。",
                    evidence_ids=["row-60"],
                ),
            ],
        )
        result = ComposeAnswerTool(FakeChat()).run(state, {"force": True})
        self.assertTrue(result.ok)
        event = next(item for item in state.trace if item["event"] == "compose_evidence")
        self.assertEqual(event["labels"], ["E2", "E1"])
        self.assertEqual(event["mapping"][0]["evidence_ids"], ["row-60"])
        compact = state_to_dict(state)
        self.assertEqual(compact["compose_evidence_map"], event["mapping"])


if __name__ == "__main__":
    unittest.main()
