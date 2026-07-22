from __future__ import annotations

import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from benchmark_common import AUDIT_PATH, EVIDENCE_PATH, GRAPH_PATH, QUESTIONS_PATH, index_by_id, load_jsonl  # noqa: E402
from score_answers import claim_supported_by_context, score_row as score_answer_row  # noqa: E402
from score_kg import score_one  # noqa: E402
from score_retrieval import row_score as score_retrieval_row  # noqa: E402
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
)
from run_harness_benchmark import prepare_output, state_to_result_row  # noqa: E402
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
        }
        retrieval = score_retrieval_row(result, question, edges)
        answer = score_answer_row(result, question, 0.72)
        self.assertAlmostEqual(retrieval["evidence"]["f1"], 1.0)
        self.assertTrue(retrieval["gold_path_complete"])
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


if __name__ == "__main__":
    unittest.main()
