from __future__ import annotations

import sys
import tempfile
import unittest
from collections import Counter
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import run_harness_benchmark as harness_runner  # noqa: E402
from benchmark_common import (  # noqa: E402
    AUDIT_PATH,
    EVIDENCE_PATH,
    GRAPH_PATH,
    QUESTIONS_PATH,
    SCHEMA_PATH,
    attach_run_identity,
    build_run_manifest,
    canonical_json_sha256,
    index_by_id,
    load_jsonl,
    resolve_index_identity,
    review_content_sha256,
    validate_result_records,
    write_json,
    write_jsonl,
)
from benchmark_contract import (  # noqa: E402
    KG_RELATION_ENDPOINTS,
    KG_SCHEMA_TYPES,
    graph_edge_is_schema_legal,
    load_kg_contract,
)
from freeze_benchmark import validate_review_bindings  # noqa: E402
from json_schema_validator import load_schema, validate_definition  # noqa: E402
from reg_harness.types import AgentState  # noqa: E402
from run_graphrag_benchmark import (  # noqa: E402
    answer_contract,
    build_answer_prompts,
    evidence_for_text,
    extract_focus_terms,
    item_relevance_score,
    oracle_items,
    post_validate_prediction,
    prioritize_items,
    token_estimate,
    trim_items,
)
from run_harness_benchmark import prepare_output, state_to_result_row  # noqa: E402
from score_answers import (  # noqa: E402
    claim_scores,
    claim_supported_by_context,
    expand_citation_ids,
    score_row as score_answer_row,
)
from score_kg import score_edges, score_one  # noqa: E402
from score_retrieval import row_score as score_retrieval_row  # noqa: E402
from validate_benchmark import EXPECTED_TASK_COUNTS  # noqa: E402


class BenchmarkDataTest(unittest.TestCase):
    def test_question_quota_and_splits(self) -> None:
        questions = load_jsonl(QUESTIONS_PATH)
        self.assertEqual(len(questions), 60)
        self.assertEqual(Counter(item["task_type"] for item in questions), Counter(EXPECTED_TASK_COUNTS))
        self.assertEqual(Counter(item["split"] for item in questions), Counter({"dev": 12, "test": 48}))

    def test_gold_references_exist(self) -> None:
        evidence_ids = {item["id"] for item in load_jsonl(EVIDENCE_PATH)}
        graph_ids = {item["id"] for item in load_jsonl(GRAPH_PATH)}
        for question in load_jsonl(QUESTIONS_PATH):
            self.assertTrue(set(question["gold_evidence_ids"]).issubset(evidence_ids))
            self.assertTrue(set(question["gold_nodes"]).issubset(graph_ids))
            self.assertTrue(set(question["gold_edges"]).issubset(graph_ids))
            self.assertEqual(question["expected_hops"], len(question["gold_path"]))

    def test_audit_balance(self) -> None:
        units = load_jsonl(AUDIT_PATH)
        self.assertEqual(Counter(item["kind"] for item in units), Counter({"narrative": 5, "table": 5}))

    def test_gold_graph_scores_as_perfect_audit_prediction(self) -> None:
        report = score_one(GRAPH_PATH, 0.72)
        self.assertAlmostEqual(report["audit_macro"]["entity_f1"], 1.0)
        self.assertAlmostEqual(report["audit_macro"]["relation_f1"], 1.0)
        self.assertAlmostEqual(report["audit_macro"]["numeric_tuple_exact_match_f1"], 1.0)
        self.assertAlmostEqual(report["task_graph"]["gold_path"]["complete_path_recall"], 1.0)

    def test_evidence_is_precisely_scoped(self) -> None:
        evidence = index_by_id(load_jsonl(EVIDENCE_PATH), "evidence")
        table_rows = [item for item in evidence.values() if item["locator"].get("row")]
        self.assertEqual(len(table_rows), 10)
        self.assertTrue(all(item["source_excerpt"].startswith("<tr>") for item in table_rows))
        self.assertTrue(all(item["source_excerpt"].endswith("</tr>") for item in table_rows))
        self.assertLess(len(evidence["unece_r152:annex3:appendix2"]["source_excerpt"]), 1500)

    def test_oracle_result_scores_perfectly(self) -> None:
        question = load_jsonl(QUESTIONS_PATH)[0]
        edges = index_by_id(
            (item for item in load_jsonl(GRAPH_PATH) if item.get("kind") == "edge"),
            "edge",
        )
        prediction = {
            "answerable": True,
            "answer": question["gold_answer"],
            "claims": [item["text"] for item in question["atomic_claims"]],
            "citations": question["gold_evidence_ids"],
            "claim_citations": {
                str(index): item["evidence_ids"]
                for index, item in enumerate(question["atomic_claims"])
            },
        }
        result = {
            "question_id": question["id"],
            "mode": "oracle",
            "retrieved_evidence_ids": question["gold_evidence_ids"],
            "ranked_evidence_ids": question["gold_evidence_ids"],
            "retrieved_items": [
                {
                    "evidence_ids": question["gold_evidence_ids"],
                    "token_estimate": 100,
                }
            ],
            "prediction": prediction,
            "result_status": "completed",
        }
        retrieval = score_retrieval_row(result, question, edges)
        answer = score_answer_row(result, question, 0.72)
        self.assertAlmostEqual(retrieval["evidence"]["f1"], 1.0)
        self.assertIsNone(retrieval["gold_path_complete"])
        self.assertTrue(retrieval["gold_path_evidence_support_complete"])
        self.assertAlmostEqual(answer["primary_score"], 1.0)
        self.assertAlmostEqual(answer["atomic_claims"]["f1"], 1.0)
        self.assertAlmostEqual(answer["faithfulness_to_retrieved_context"], 1.0)

    def test_evidence_mapping_does_not_cross_documents_on_clause_number(self) -> None:
        evidence = load_jsonl(EVIDENCE_PATH)
        matched = evidence_for_text(
            "relation_type=APPLIES_TO; source_clause:1; evidence=本文件适用于M1和N1类汽车。",
            "GB+39901-2025.pdf_by_PaddleOCR-VL-1.6__narrative_001.md",
            evidence,
        )
        self.assertIn("gb39901:clause:1", matched)
        self.assertFalse(any(item.startswith(("unece_", "euroncap_")) for item in matched))

    def test_clause_mapping_requires_an_exact_marker(self) -> None:
        evidence = load_jsonl(EVIDENCE_PATH)
        matched = evidence_for_text(
            "relation_type=SPECIFIES; source_clause=6.1.1; evidence=试验车辆载荷应分别设置。",
            "GB+39901-2025.pdf_by_PaddleOCR-VL-1.6__narrative_009.md",
            evidence,
        )
        self.assertIn("gb39901:clause:6.1.1", matched)
        self.assertNotIn("gb39901:clause:1", matched)
        self.assertNotIn("gb39901:clause:5.6", matched)
        self.assertNotIn("gb39901:clause:6.11", matched)

    def test_grouped_clause_evidence_matches_member_clause(self) -> None:
        evidence = load_jsonl(EVIDENCE_PATH)
        matched = evidence_for_text(
            "relation_type=VERIFIED_BY; source_clause=6.6; evidence=匀速车辆目标试验。",
            "GB+39901-2025.pdf_by_PaddleOCR-VL-1.6__narrative_011.md",
            evidence,
        )
        self.assertIn("gb39901:clause:6.5-6.7", matched)

    def test_parent_clause_evidence_matches_explicit_child_clause(self) -> None:
        evidence = load_jsonl(EVIDENCE_PATH)
        matched = evidence_for_text(
            "relation_type=SPECIFIES; source_clause=6.1.1.1; evidence=两组载荷条件。",
            "GB+39901-2025.pdf_by_PaddleOCR-VL-1.6__narrative_009.md",
            evidence,
        )
        self.assertIn("gb39901:clause:6.1.1", matched)
        self.assertNotIn("gb39901:clause:1", matched)

    def test_oracle_table_row_includes_schema_context(self) -> None:
        evidence = index_by_id(load_jsonl(EVIDENCE_PATH), "evidence")
        question = index_by_id(load_jsonl(QUESTIONS_PATH), "question")["gb_table_002"]
        item = oracle_items(question, evidence)[0]
        self.assertIn("normalized_facts", item["text"])
        self.assertIn('"gross_kmh": 10', item["text"])

    def test_answer_contract_is_independent_of_gold_fields(self) -> None:
        question = index_by_id(load_jsonl(QUESTIONS_PATH), "question")["gb_direct_001"]
        contract = answer_contract(question)
        self.assertNotIn("M1", str(contract))
        self.assertNotIn("vehicle_categories", str(contract))
        self.assertNotEqual(contract.get("answerable"), True)
        self.assertNotEqual(contract.get("answerable"), False)
        self.assertIsInstance(contract.get("answerable"), str)

    def test_answer_prompts_do_not_include_evaluation_labels(self) -> None:
        question = "N1 类 80 km/h 时表中是否有对应试验行？"
        system, user = build_answer_prompts(
            question, "[R1] 表2没有80 km/h行", "hybrid"
        )
        prompt = system + user
        self.assertNotIn("task_type", prompt)
        self.assertNotIn("unanswerable_adversarial", prompt)
        self.assertNotIn("scoring_method", prompt)
        self.assertNotIn("gold_answer", prompt)
        self.assertNotIn("优先拒答", prompt)

    def test_p0_focus_terms_from_question_only(self) -> None:
        question = index_by_id(load_jsonl(QUESTIONS_PATH), "question")["gb_table_002"]
        terms = extract_focus_terms(question)
        self.assertIn("N1", terms)
        self.assertIn("40", terms)
        self.assertIn("__prefer_table__", terms)
        # Must not leak gold answers into focus extraction.
        self.assertNotIn("10", terms)

    def test_p0_prioritize_prefers_chunks_in_hybrid(self) -> None:
        question = {
            "id": "demo",
            "question": "N1 类 40 km/h 最大设计总质量 静止车辆目标 最大相对碰撞速度？",
            "task_type": "conditional_table",
        }
        noisy_entity = {
            "kind": "entity",
            "text": "AEBS [System]\n自动紧急制动系统的一般描述，无表格数值。",
            "file_path": "narrative.md",
            "evidence_ids": [],
            "token_estimate": token_estimate("AEBS [System]\n自动紧急制动系统的一般描述，无表格数值。"),
        }
        goldish_chunk = {
            "kind": "chunk",
            "text": "<tr><td>N1</td><td>40</td><td>0</td><td>最大设计总质量</td><td>10</td></tr>",
            "file_path": "GB+39901-2025__table_2.md",
            "evidence_ids": ["gb39901:table:2:row:40"],
            "token_estimate": token_estimate(
                "<tr><td>N1</td><td>40</td><td>0</td><td>最大设计总质量</td><td>10</td></tr>"
            ),
        }
        relation = {
            "kind": "relationship",
            "text": "Requirement --HAS_THRESHOLD--> Threshold\n一般性能要求",
            "file_path": "narrative.md",
            "evidence_ids": [],
            "token_estimate": token_estimate("Requirement --HAS_THRESHOLD--> Threshold\n一般性能要求"),
        }
        selected = prioritize_items(
            [noisy_entity, relation, goldish_chunk],
            question,
            "hybrid",
            max_tokens=500,
            context_policy="compact",
        )
        self.assertEqual(selected[0]["kind"], "chunk")
        self.assertGreater(
            item_relevance_score(goldish_chunk, extract_focus_terms(question), "hybrid"),
            item_relevance_score(noisy_entity, extract_focus_terms(question), "hybrid"),
        )

    def test_p0_post_validate_blocks_ungrounded_speed(self) -> None:
        items = [
            {
                "kind": "chunk",
                "text": "表2仅给出60 km/h与40 km/h行，没有80 km/h行。",
                "file_path": "table_2.md",
                "evidence_ids": ["gb39901:table:2"],
                "token_estimate": 40,
            }
        ]
        prediction = {
            "answerable": True,
            "answer": {"max_relative_collision_speed": 50, "unit": "km/h"},
            "claims": ["阈值为50"],
            "citations": [],
        }
        question = {
            "id": "gb_unanswerable_002",
            "question": "N1 80 km/h 阈值？",
            "task_type": "unanswerable_adversarial",
            "scoring_method": "unanswerable",
        }
        checked = post_validate_prediction(prediction, items, question, "hybrid")
        self.assertFalse(checked["answerable"])
        self.assertTrue(any("forced_refusal_ungrounded_numeric" in flag for flag in checked["validation_flags"]))

    def test_p0_post_validate_empty_context_refusal(self) -> None:
        prediction = {"answerable": True, "answer": {"vehicle_categories": ["M1"]}, "claims": [], "citations": []}
        checked = post_validate_prediction(prediction, [], {"id": "x", "scoring_method": "structured_exact_match"}, "mix")
        self.assertFalse(checked["answerable"])
        self.assertIn("forced_refusal_empty_context", checked["validation_flags"])

    def test_faithfulness_requires_numbers_in_same_matching_condition(self) -> None:
        context = "M1 类阈值为 35 km/h。\nN1 类阈值为 40 km/h。"
        self.assertFalse(
            claim_supported_by_context("M1 类阈值为 40 km/h", context)
        )
        self.assertTrue(
            claim_supported_by_context("N1 类阈值为 40 km/h", context)
        )

    def test_no_resume_clears_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.jsonl"
            path.write_text(
                '{"question_id":"q1","mode":"harness_skill"}\n',
                encoding="utf-8",
            )
            completed = prepare_output(path, mode="harness_skill", resume=False)
            self.assertEqual(completed, set())
            self.assertEqual(path.read_text(encoding="utf-8"), "")

    def test_harness_result_preserves_evidence_rank(self) -> None:
        state = SimpleNamespace(
            final_answer={"answerable": False},
            evidence=[
                SimpleNamespace(
                    evidence_ids=["z", "a"], kind="chunk", file_path="", text="one"
                ),
                SimpleNamespace(
                    evidence_ids=["z", "b"], kind="chunk", file_path="", text="two"
                ),
            ],
            step=1,
            trace=[],
        )
        row = state_to_result_row(
            {"id": "q", "split": "dev"},
            state,
            mode="harness_skill",
            latency=0.1,
        )
        self.assertEqual(row["ranked_evidence_ids"], ["z", "a", "b"])
        self.assertEqual(row["retrieved_evidence_ids"], ["a", "b", "z"])


class BenchmarkIntegrityRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.questions = index_by_id(load_jsonl(QUESTIONS_PATH), "question")
        cls.evidence = index_by_id(load_jsonl(EVIDENCE_PATH), "evidence")
        graph = load_jsonl(GRAPH_PATH)
        cls.nodes = index_by_id(
            (item for item in graph if item.get("kind") == "node"),
            "node",
        )
        cls.edges = index_by_id(
            (item for item in graph if item.get("kind") == "edge"),
            "edge",
        )

    @staticmethod
    def _manifest(
        question_ids: list[str],
        *,
        mode: str = "naive",
        revision: int = 1,
    ) -> dict:
        return build_run_manifest(
            runner="unit_test",
            selected_question_ids=question_ids,
            modes=[mode],
            configuration={"revision": revision},
        )

    @staticmethod
    def _index_fingerprint(
        *,
        workspace: str = "ws",
        status: str = "ready",
        source_sha256: str = "a" * 64,
    ) -> dict:
        inputs = {
            "mode": "structural_bundle",
            "bundle_file": "corpus/index_ready/units.json",
            "bundle_sha256": "b" * 64,
            "source_id": "gb",
            "source_file": "corpus/prepared/gb.md",
            "source_sha256": source_sha256,
            "unit_count": 2,
        }
        return {
            "schema_version": 2,
            "status": status,
            "workspace": workspace,
            "sha256": "e" * 64,
            "config": {
                "binding": "openai",
                "host": "https://embed.invalid/v1",
                "model": "m",
                "dimension": 8,
                "token_limit": 1024,
            },
            "corpus": {
                "sha256": canonical_json_sha256(inputs),
                "inputs": inputs,
            },
        }

    def test_missing_index_fingerprint_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(
                RuntimeError,
                "Missing ready index fingerprint",
            ):
                resolve_index_identity(
                    workspace="ws",
                    state_dir=Path(tmp),
                )

    def test_nonready_index_fingerprint_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            write_json(
                state / "embedding_fingerprint.ws.json",
                self._index_fingerprint(status="indexing"),
            )
            with self.assertRaisesRegex(RuntimeError, "not ready"):
                resolve_index_identity(workspace="ws", state_dir=state)

    def test_index_drift_changes_manifest_and_rejects_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            path = state / "embedding_fingerprint.ws.json"
            write_json(path, self._index_fingerprint(source_sha256="a" * 64))
            identity_one = resolve_index_identity(
                workspace="ws",
                state_dir=state,
            )
            write_json(path, self._index_fingerprint(source_sha256="c" * 64))
            identity_two = resolve_index_identity(
                workspace="ws",
                state_dir=state,
            )
        manifest_one = build_run_manifest(
            runner="unit_test",
            selected_question_ids=["q1"],
            modes=["naive"],
            configuration={"index_identity": identity_one},
        )
        manifest_two = build_run_manifest(
            runner="unit_test",
            selected_question_ids=["q1"],
            modes=["naive"],
            configuration={"index_identity": identity_two},
        )
        self.assertNotEqual(
            manifest_one["fingerprint"],
            manifest_two["fingerprint"],
        )
        record = attach_run_identity(
            {"question_id": "q1", "mode": "naive"},
            run_id="run-1",
            manifest=manifest_one,
        )
        with self.assertRaisesRegex(RuntimeError, "Resume configuration"):
            validate_result_records(
                [record],
                expected_manifest=manifest_two,
            )

    def test_explicit_remote_index_identity_is_stable_and_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            first = resolve_index_identity(
                workspace="remote_ws",
                state_dir=state,
                explicit_fingerprint="remote-build-20260728-001",
            )
            repeated = resolve_index_identity(
                workspace="remote_ws",
                state_dir=state,
                explicit_fingerprint="remote-build-20260728-001",
            )
            second = resolve_index_identity(
                workspace="remote_ws",
                state_dir=state,
                explicit_fingerprint="remote-build-20260728-002",
            )
        self.assertEqual(first, repeated)
        self.assertEqual(first["source"], "explicit_remote_id")
        self.assertNotEqual(first["content_sha256"], second["content_sha256"])

    def test_published_pilot_questions_are_all_dev(self) -> None:
        pilot = {
            "gb_direct_001",
            "gb_table_002",
            "gb_multi_hop_009",
            "gb_compare_002",
            "gb_synthesis_001",
            "gb_unanswerable_002",
        }
        self.assertTrue(all(self.questions[item]["split"] == "dev" for item in pilot))

    def test_reasoning_and_extractable_graph_roles_are_explicit(self) -> None:
        roles = Counter(
            item["properties"]["graph_role"]
            for item in [*self.nodes.values(), *self.edges.values()]
        )
        self.assertGreater(roles["reasoning"], 0)
        self.assertGreater(roles["extractable_kg"], 0)

    def test_gold_kg_paths_are_schema_legal_and_source_scoped(self) -> None:
        evaluable = 0
        for question in self.questions.values():
            for edge_id in question["gold_kg_path"]:
                evaluable += 1
                self.assertTrue(
                    graph_edge_is_schema_legal(self.edges[edge_id], self.nodes)
                )
                self.assertTrue(
                    all(
                        evidence_id.startswith("gb39901:")
                        for evidence_id in self.edges[edge_id]["evidence_ids"]
                    )
                )
        self.assertGreater(evaluable, 0)

    def test_kg_contract_is_loaded_from_yaml_single_source(self) -> None:
        types, relations = load_kg_contract()
        self.assertEqual(types, KG_SCHEMA_TYPES)
        self.assertEqual(relations, KG_RELATION_ENDPOINTS)

    def test_json_schema_rejects_missing_required_question_field(self) -> None:
        broken = deepcopy(next(iter(self.questions.values())))
        broken.pop("gold_kg_path")
        errors = validate_definition(
            [broken],
            schema=load_schema(SCHEMA_PATH),
            definition="question",
            label="question",
        )
        self.assertTrue(any("gold_kg_path" in error for error in errors))

    def test_empty_kg_prediction_has_complete_metric_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.jsonl"
            path.write_text("", encoding="utf-8")
            report = score_one(path, 0.72)
        self.assertEqual(report["audit_macro"]["entity_f1"], 0.0)
        self.assertEqual(
            report["audit_macro"]["numeric_tuple_exact_match_f1"],
            0.0,
        )
        self.assertTrue(
            all(
                "f1" in row["numeric_condition_tuples"]
                and "accuracy" in row["evidence_binding"]
                for row in report["audit_units"]
            )
        )

    def test_kg_edge_matching_is_one_to_one(self) -> None:
        gold = [
            {"id": "g1", "source": "gs", "relation": "SPECIFIES", "target": "gt"},
            {"id": "g2", "source": "gs", "relation": "SPECIFIES", "target": "gt"},
        ]
        predicted = [
            {"id": "p1", "source": "ps", "relation": "SPECIFIES", "target": "pt"}
        ]
        metrics, matches = score_edges(
            gold,
            predicted,
            {"gs": "ps", "gt": "pt"},
        )
        self.assertEqual(metrics["true_positive"], 1)
        self.assertEqual(len(matches), 1)

    def test_schema_invalid_predicted_edge_cannot_complete_kg_path(self) -> None:
        question = self.questions["gb_multi_hop_001"]
        node_ids = {
            endpoint
            for edge_id in question["gold_kg_path"]
            for endpoint in (
                self.edges[edge_id]["source"],
                self.edges[edge_id]["target"],
            )
        }
        records = [deepcopy(self.nodes[item]) for item in sorted(node_ids)]
        for index, edge_id in enumerate(question["gold_kg_path"]):
            edge = deepcopy(self.edges[edge_id])
            if index == 0:
                edge["schema_valid"] = False
            records.append(edge)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invalid-edge.jsonl"
            write_jsonl(path, records)
            report = score_one(path, 0.72, source_set="gb", split="dev")
        rows = report["task_graph"]["gold_path"]["per_question"]
        scored = next(item for item in rows if item["question_id"] == question["id"])
        self.assertFalse(scored["complete"])

    def test_unrelated_table_text_does_not_credit_all_rows(self) -> None:
        matched = evidence_for_text(
            "无任何表格正文",
            "GB+39901-2025.pdf_by_PaddleOCR-VL-1.6__table_2.md",
            list(self.evidence.values()),
        )
        self.assertEqual(matched, ["gb39901:table:2"])

    def test_exact_table_row_does_not_credit_sibling_row(self) -> None:
        matched = evidence_for_text(
            self.evidence["gb39901:table:2:row:40"]["source_excerpt"],
            "GB+39901-2025.pdf_by_PaddleOCR-VL-1.6__table_2.md",
            list(self.evidence.values()),
        )
        self.assertIn("gb39901:table:2:row:40", matched)
        self.assertNotIn("gb39901:table:2:row:60", matched)

    def test_truncation_recomputes_removed_row_evidence(self) -> None:
        first = self.evidence["gb39901:table:2:row:40"]["source_excerpt"]
        second = self.evidence["gb39901:table:2:row:60"]["source_excerpt"]
        text = first + ("\n填充" * 200) + second
        item = {
            "kind": "chunk",
            "text": text,
            "file_path": "GB+39901-2025.pdf_by_PaddleOCR-VL-1.6__table_2.md",
            "evidence_ids": [
                "gb39901:table:2",
                "gb39901:table:2:row:40",
                "gb39901:table:2:row:60",
            ],
            "token_estimate": token_estimate(text),
        }
        selected = trim_items(
            [item],
            token_estimate(first) + 2,
            list(self.evidence.values()),
        )
        self.assertTrue(selected[0]["truncated"])
        self.assertIn("gb39901:table:2:row:40", selected[0]["evidence_ids"])
        self.assertNotIn("gb39901:table:2:row:60", selected[0]["evidence_ids"])

    def test_true_graph_path_is_not_inferred_from_evidence_overlap(self) -> None:
        question = self.questions["gb_multi_hop_001"]
        result = {
            "question_id": question["id"],
            "mode": "hybrid",
            "retrieved_evidence_ids": question["gold_evidence_ids"],
            "ranked_evidence_ids": question["gold_evidence_ids"],
            "retrieved_items": [],
        }
        scored = score_retrieval_row(result, question, self.edges, self.nodes)
        self.assertTrue(scored["gold_path_evidence_support_complete"])
        self.assertFalse(scored["gold_path_complete"])

    def test_half_graph_path_is_incomplete(self) -> None:
        question = self.questions["gb_multi_hop_001"]
        gold = self.edges[question["gold_kg_path"][0]]
        result = {
            "question_id": question["id"],
            "mode": "hybrid",
            "retrieved_evidence_ids": question["gold_evidence_ids"],
            "retrieved_graph_edges": [
                {
                    "source": self.nodes[gold["source"]]["name"],
                    "relation": gold["relation"],
                    "target": self.nodes[gold["target"]]["name"],
                }
            ],
            "retrieved_items": [],
        }
        scored = score_retrieval_row(result, question, self.edges, self.nodes)
        self.assertLess(scored["gold_path_edge_recall"], 1.0)
        self.assertFalse(scored["gold_path_complete"])

    def test_full_connected_graph_path_is_complete(self) -> None:
        question = self.questions["gb_multi_hop_001"]
        retrieved = []
        for edge_id in question["gold_kg_path"]:
            edge = self.edges[edge_id]
            retrieved.append(
                {
                    "source": self.nodes[edge["source"]]["name"],
                    "relation": edge["relation"],
                    "target": self.nodes[edge["target"]]["name"],
                }
            )
        result = {
            "question_id": question["id"],
            "mode": "hybrid",
            "retrieved_evidence_ids": question["gold_evidence_ids"],
            "retrieved_graph_edges": retrieved,
            "retrieved_items": [],
        }
        scored = score_retrieval_row(result, question, self.edges, self.nodes)
        self.assertTrue(scored["gold_path_complete"])
        self.assertTrue(scored["gold_path_graph"]["connected"])

    def test_graph_path_connectivity_accepts_node_aliases(self) -> None:
        nodes = {
            "a": {"id": "a", "name": "系统 A", "aliases": []},
            "b": {
                "id": "b",
                "name": "自动紧急制动系统",
                "aliases": ["AEB"],
            },
            "c": {"id": "c", "name": "目标 C", "aliases": []},
        }
        edges = {
            "e1": {"source": "a", "relation": "R1", "target": "b"},
            "e2": {"source": "b", "relation": "R2", "target": "c"},
        }
        question = {
            "id": "alias_path",
            "task_type": "multi_hop_relation",
            "answerable": True,
            "gold_evidence_ids": [],
            "gold_reasoning_path": [],
            "gold_kg_path": ["e1", "e2"],
        }
        result = {
            "question_id": question["id"],
            "mode": "hybrid",
            "retrieved_evidence_ids": [],
            "retrieved_graph_edges": [
                {"source": "系统 A", "relation": "R1", "target": "AEB"},
                {
                    "source": "自动紧急制动系统",
                    "relation": "R2",
                    "target": "目标 C",
                },
            ],
            "retrieved_items": [],
        }

        scored = score_retrieval_row(result, question, edges, nodes)

        self.assertEqual(scored["gold_path_graph"]["matched_edges"], 2)
        self.assertTrue(scored["gold_path_graph"]["connected"])
        self.assertTrue(scored["gold_path_complete"])

    def test_timeout_refusal_never_scores_as_correct(self) -> None:
        question = self.questions["gb_unanswerable_005"]
        result = {
            "question_id": question["id"],
            "mode": "harness_skill",
            "prediction": {
                "answerable": False,
                "answer": {},
                "claims": [],
                "citations": [],
                "reason": "证据不足，无法回答",
            },
            "error": "TimeoutError: request timed out",
            "result_status": "error",
        }
        scored = score_answer_row(result, question, 0.72)
        self.assertEqual(scored["primary_score"], 0.0)
        self.assertFalse(scored["valid_result"])

    def test_valid_evidence_refusal_scores_as_correct(self) -> None:
        question = self.questions["gb_unanswerable_005"]
        result = {
            "question_id": question["id"],
            "mode": "oracle",
            "prediction": {
                "answerable": False,
                "answer": {},
                "claims": [],
                "citations": [],
                "reason": "现有证据缺少该前提，无法推出所问结论",
            },
            "result_status": "completed",
        }
        self.assertEqual(score_answer_row(result, question, 0.72)["primary_score"], 1.0)

    def test_refusal_with_claims_or_citations_is_invalid(self) -> None:
        question = self.questions["gb_unanswerable_005"]
        result = {
            "question_id": question["id"],
            "mode": "oracle",
            "prediction": {
                "answerable": False,
                "answer": {},
                "claims": ["无依据声明"],
                "citations": ["fake"],
                "reason": "证据不足",
            },
            "result_status": "completed",
        }
        self.assertEqual(score_answer_row(result, question, 0.72)["primary_score"], 0.0)

    def test_refusal_reason_must_express_insufficiency(self) -> None:
        question = self.questions["gb_unanswerable_005"]
        result = {
            "question_id": question["id"],
            "mode": "oracle",
            "prediction": {
                "answerable": False,
                "answer": {},
                "claims": [],
                "citations": [],
                "reason": "现有证据充分，前提已经满足",
            },
            "result_status": "completed",
        }
        self.assertEqual(score_answer_row(result, question, 0.72)["primary_score"], 0.0)

    def test_missing_result_status_is_not_a_valid_refusal(self) -> None:
        question = self.questions["gb_unanswerable_005"]
        result = {
            "question_id": question["id"],
            "mode": "oracle",
            "prediction": {
                "answerable": False,
                "answer": {},
                "claims": [],
                "citations": [],
                "reason": "证据不足，无法回答",
            },
        }
        scored = score_answer_row(result, question, 0.72)
        self.assertEqual(scored["primary_score"], 0.0)
        self.assertFalse(scored["valid_result"])

    def test_negated_claim_cannot_match_positive_claim(self) -> None:
        score = claim_scores(["系统不应发出预警"], ["系统应发出预警"], 0.0)
        self.assertEqual(score["f1"], 0.0)

    def test_comparator_inversion_cannot_match(self) -> None:
        score = claim_scores(["阈值小于0.8 s"], ["阈值不小于0.8 s"], 0.0)
        self.assertEqual(score["f1"], 0.0)

    def test_numeric_unit_conflict_cannot_match(self) -> None:
        score = claim_scores(["阈值为60 s"], ["阈值为60 km/h"], 0.0)
        self.assertEqual(score["f1"], 0.0)

    def test_numeric_unit_conflict_is_not_faithful_to_context(self) -> None:
        self.assertFalse(
            claim_supported_by_context(
                "系统在60 s时触发",
                "系统在60 km/h时触发。",
            )
        )

    def test_result_validator_rejects_duplicate_keys(self) -> None:
        manifest = self._manifest(["q1"])
        row = attach_run_identity(
            {"question_id": "q1", "mode": "naive"},
            run_id="run-1",
            manifest=manifest,
        )
        with self.assertRaisesRegex(RuntimeError, "Duplicate result key"):
            validate_result_records([row, deepcopy(row)])

    def test_result_validator_rejects_mixed_runs(self) -> None:
        first_manifest = self._manifest(["q1"], revision=1)
        second_manifest = self._manifest(["q2"], revision=2)
        rows = [
            attach_run_identity(
                {"question_id": "q1", "mode": "naive"},
                run_id="run-1",
                manifest=first_manifest,
            ),
            attach_run_identity(
                {"question_id": "q2", "mode": "naive"},
                run_id="run-2",
                manifest=second_manifest,
            ),
        ]
        with self.assertRaisesRegex(RuntimeError, "Mixed benchmark runs"):
            validate_result_records(rows)

    def test_result_validator_rejects_legacy_manifest_format(self) -> None:
        manifest = self._manifest(["q1"])
        manifest["format_version"] = 1
        # Recompute the fingerprint so this specifically exercises the version
        # gate rather than the tamper check.
        manifest["fingerprint"] = canonical_json_sha256(
            {key: value for key, value in manifest.items() if key != "fingerprint"}
        )
        row = attach_run_identity(
            {"question_id": "q1", "mode": "naive"},
            run_id="run-1",
            manifest=manifest,
        )
        with self.assertRaisesRegex(RuntimeError, "unsupported run_manifest"):
            validate_result_records([row])

    def test_resume_manifest_must_match_exact_configuration(self) -> None:
        manifest = self._manifest(["q1"], revision=1)
        row = attach_run_identity(
            {"question_id": "q1", "mode": "naive"},
            run_id="run-1",
            manifest=manifest,
        )
        with self.assertRaisesRegex(RuntimeError, "Resume configuration"):
            validate_result_records(
                [row],
                expected_manifest=self._manifest(["q1"], revision=2),
            )

    def test_result_key_must_be_inside_manifest_selection(self) -> None:
        manifest = self._manifest(["q1"])
        row = attach_run_identity(
            {"question_id": "q2", "mode": "naive"},
            run_id="run-1",
            manifest=manifest,
        )
        with self.assertRaisesRegex(RuntimeError, "outside"):
            validate_result_records([row])

    def test_review_hash_changes_with_reviewed_content(self) -> None:
        question = self.questions["gb_direct_001"]
        original = review_content_sha256(
            question,
            self.evidence,
            self.nodes,
            self.edges,
        )
        changed = deepcopy(question)
        changed["question"] += "（已修改）"
        self.assertNotEqual(
            original,
            review_content_sha256(
                changed,
                self.evidence,
                self.nodes,
                self.edges,
            ),
        )

    def test_freeze_rejects_stale_review_hash(self) -> None:
        question = self.questions["gb_direct_001"]
        reviews = {
            question["id"]: {
                "id": question["id"],
                "review_decision": "通过",
                "content_sha256": "0" * 64,
            }
        }
        with self.assertRaisesRegex(RuntimeError, "stale"):
            validate_review_bindings(
                reviews,
                [question],
                self.evidence,
                self.nodes,
                self.edges,
            )

    def test_harness_result_uses_actual_rendered_label_map(self) -> None:
        state = SimpleNamespace(
            final_answer={
                "answerable": True,
                "answer": {"value": 1},
                "claims": ["one"],
                "citations": ["E2"],
            },
            evidence=[
                SimpleNamespace(
                    evidence_ids=["a"], kind="entity", file_path="", text="one"
                ),
                SimpleNamespace(
                    evidence_ids=["b"], kind="chunk", file_path="", text="two"
                ),
            ],
            meta={
                "compose_evidence_map": [
                    {
                        "label": "E2",
                        "evidence_index": 1,
                        "evidence_ids": ["b"],
                    }
                ]
            },
            step=1,
            trace=[],
        )
        row = state_to_result_row(
            {"id": "q", "split": "dev"},
            state,
            mode="harness_skill",
            latency=0.1,
        )
        self.assertEqual(row["reference_map"], {"E2": ["b"]})
        self.assertEqual(row["rendered_evidence_labels"], ["E2"])
        self.assertIsNone(row["retrieved_items"][0]["rendered_label"])

    def test_missing_rendered_label_never_falls_back_to_bag_position(self) -> None:
        result = {
            "reference_map": {"E2": ["b"]},
            "retrieved_items": [{"evidence_ids": ["a"]}, {"evidence_ids": ["b"]}],
        }
        self.assertEqual(expand_citation_ids(["E1"], result), {"E1"})

    def test_score_kg_source_and_split_selection_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.jsonl"
            path.write_text("", encoding="utf-8")
            dev = score_one(path, 0.72, source_set="gb", split="dev")
            test = score_one(path, 0.72, source_set="gb", split="test")
        self.assertEqual(dev["selection"]["question_count"], 12)
        self.assertEqual(test["selection"]["question_count"], 38)
        self.assertEqual(dev["selection"]["schema_evaluable_question_count"], 1)
        self.assertEqual(test["selection"]["schema_evaluable_question_count"], 5)

    def test_harness_runner_closes_stack_after_normal_return(self) -> None:
        stack = MagicMock()
        stack.describe.return_value = {}
        args = SimpleNamespace(
            profile_env=".env.test",
            output=Path("unused.jsonl"),
            mode_name="harness_skill",
            max_steps=1,
            skip_score=True,
            claim_threshold=0.72,
            source="gb",
            score_output=Path("unused-score.json"),
        )
        manifest = build_run_manifest(
            runner="unit_test",
            selected_question_ids=[],
            modes=[args.mode_name],
            configuration={},
        )
        with (
            patch("reg_harness.runtime.build_stack", return_value=stack),
            patch("builtins.print"),
        ):
            result = harness_runner._run_managed_benchmark(
                settings=SimpleNamespace(),
                args=args,
                pending=[],
                manifest=manifest,
                run_id="run-test",
                all_records=[],
            )

        self.assertEqual(result, 0)
        stack.close.assert_called_once()

    def test_harness_runner_closes_stack_when_atomic_write_fails(self) -> None:
        stack = MagicMock()
        stack.describe.return_value = {}
        stack.ask.return_value = AgentState(question="question")
        args = SimpleNamespace(
            profile_env=".env.test",
            output=Path("unused.jsonl"),
            mode_name="harness_skill",
            max_steps=1,
            skip_score=True,
            claim_threshold=0.72,
            source="gb",
            score_output=Path("unused-score.json"),
        )
        manifest = build_run_manifest(
            runner="unit_test",
            selected_question_ids=["q1"],
            modes=[args.mode_name],
            configuration={},
        )
        pending = [
            {
                "id": "q1",
                "question": "question",
                "split": "dev",
                "task_type": "direct_lookup",
                "scoring_method": "exact",
            }
        ]
        with (
            patch("reg_harness.runtime.build_stack", return_value=stack),
            patch.object(
                harness_runner,
                "atomic_write_jsonl",
                side_effect=RuntimeError("atomic write failed"),
            ),
            patch("builtins.print"),
        ):
            with self.assertRaisesRegex(RuntimeError, "atomic write failed"):
                harness_runner._run_managed_benchmark(
                    settings=SimpleNamespace(),
                    args=args,
                    pending=pending,
                    manifest=manifest,
                    run_id="run-test",
                    all_records=[],
                )

        stack.ask.assert_called_once()
        stack.close.assert_called_once()

    def test_harness_runner_closes_stack_after_ask_failure(self) -> None:
        stack = MagicMock()
        stack.describe.return_value = {}
        stack.ask.side_effect = RuntimeError("ask failed")
        args = SimpleNamespace(
            profile_env=".env.test",
            output=Path("unused.jsonl"),
            mode_name="harness_skill",
            max_steps=1,
            skip_score=True,
            claim_threshold=0.72,
            source="gb",
            score_output=Path("unused-score.json"),
        )
        manifest = build_run_manifest(
            runner="unit_test",
            selected_question_ids=["q1"],
            modes=[args.mode_name],
            configuration={},
        )
        pending = [
            {
                "id": "q1",
                "question": "question",
                "split": "dev",
                "task_type": "direct_lookup",
                "scoring_method": "exact",
            }
        ]
        with (
            patch("reg_harness.runtime.build_stack", return_value=stack),
            patch.object(harness_runner, "atomic_write_jsonl"),
            patch.object(harness_runner.traceback, "print_exc"),
            patch("builtins.print"),
        ):
            result = harness_runner._run_managed_benchmark(
                settings=SimpleNamespace(),
                args=args,
                pending=pending,
                manifest=manifest,
                run_id="run-test",
                all_records=[],
            )

        self.assertEqual(result, 2)
        stack.ask.assert_called_once()
        stack.close.assert_called_once()

    def test_harness_runner_closes_stack_when_scoring_fails(self) -> None:
        stack = MagicMock()
        stack.describe.return_value = {}
        args = SimpleNamespace(
            profile_env=".env.test",
            output=Path("unused.jsonl"),
            mode_name="harness_skill",
            max_steps=1,
            skip_score=False,
            claim_threshold=0.72,
            source="gb",
            score_output=Path("unused-score.json"),
        )
        manifest = build_run_manifest(
            runner="unit_test",
            selected_question_ids=[],
            modes=[args.mode_name],
            configuration={},
        )
        with (
            patch("reg_harness.runtime.build_stack", return_value=stack),
            patch.object(
                harness_runner,
                "validate_result_records",
                side_effect=RuntimeError("scoring failed"),
            ),
            patch("builtins.print"),
        ):
            with self.assertRaisesRegex(RuntimeError, "scoring failed"):
                harness_runner._run_managed_benchmark(
                    settings=SimpleNamespace(),
                    args=args,
                    pending=[],
                    manifest=manifest,
                    run_id="run-test",
                    all_records=[],
                )

        stack.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
