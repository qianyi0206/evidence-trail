#!/usr/bin/env python3
"""Generate the six-question pilot comparison and provisional semantic audit."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmark_common import QUESTIONS_PATH, RESULTS_DIR, load_jsonl, write_json, write_jsonl


QUESTION_IDS = [
    "gb_direct_001",
    "gb_table_002",
    "gb_multi_hop_009",
    "gb_compare_002",
    "gb_synthesis_001",
    "gb_unanswerable_002",
]
VARIANTS = ("a0", "v2", "v3", "v4")
MODES = ("naive", "hybrid", "mix")
OUTCOME_SCORE = {"pass": 1.0, "partial": 0.5, "fail": 0.0}

# Order follows QUESTION_IDS. This is a provisional Codex semantic audit, not
# the user's frozen human label. P=complete, R=partially correct, F=incorrect.
LABEL_CODES = {
    ("shared", "closed_book"): "FFFFFP",
    ("shared", "oracle"): "PPPPPP",
    ("a0", "naive"): "PFPPFP",
    ("a0", "hybrid"): "PFRRPP",
    ("a0", "mix"): "PFRRPP",
    ("v2", "naive"): "FFFPFF",
    ("v2", "hybrid"): "PFPRPF",
    ("v2", "mix"): "PFPRPF",
    ("v3", "naive"): "PPPPFP",
    ("v3", "hybrid"): "PFPFPP",
    ("v3", "mix"): "PFPFPP",
    ("v4", "naive"): "PPPPFP",
    ("v4", "hybrid"): "PPRRPP",
    ("v4", "mix"): "PFRRPP",
}
CODE_TO_OUTCOME = {"P": "pass", "R": "partial", "F": "fail"}


def json_file(name: str) -> dict[str, Any]:
    return json.loads((RESULTS_DIR / name).read_text(encoding="utf-8"))


def summary_for(payload: dict[str, Any], mode: str) -> dict[str, Any]:
    for item in payload["summaries"]:
        if item["mode"] == mode and item["task_type"] == "__all__":
            return item["metrics"]
    raise RuntimeError(f"Missing summary for mode={mode}")


def mean(metrics: dict[str, Any], name: str) -> float | None:
    value = metrics[name]["mean"]
    return None if value is None else float(value)


def semantic_rationale(question_id: str, outcome: str, variant: str, mode: str) -> str:
    if outcome == "pass":
        return {
            "gb_direct_001": "完整给出 M1 和 N1 两类适用车型。",
            "gb_table_002": "正确给出 N1、40 km/h、最大设计总质量和 10 km/h 阈值。",
            "gb_multi_hop_009": "覆盖 6.5 至 6.10 的仿真范围及五项可信度维度。",
            "gb_compare_002": "完整比较两组载荷，并保留行车质量异常时的替代规则。",
            "gb_synthesis_001": "完整枚举五类误响应场景并给出共同合格判据。",
            "gb_unanswerable_002": "正确识别 N1 的 80 km/h 条件没有法规支持并拒答。",
        }[question_id]
    if outcome == "partial":
        if question_id == "gb_multi_hop_009":
            return "仿真替代范围正确，但五项可信度维度缺失或混入 KPI、阈值等其他概念。"
        if question_id == "gb_compare_002":
            return "两组载荷要求基本正确，但异常质量关系的处理规则遗漏或被错误判为不可答。"
        return "包含部分正确事实，但未覆盖全部金答案。"
    if variant == "v2" and question_id == "gb_unanswerable_002":
        return "错误给出 50 km/h 数值，未识别问题中的 80 km/h 条件无支持。"
    if variant == "v2" and mode == "naive" and question_id == "gb_table_002":
        return "把最大设计总质量列的 10 km/h 错答为 0 km/h。"
    if variant == "v2" and mode == "naive" and question_id == "gb_synthesis_001":
        return "把试验结束条件当作共同合格判据，未准确给出不预警且不紧急制动。"
    if question_id == "gb_table_002":
        return "未从已检索表格中恢复目标单元格，选择拒答或返回空字段。"
    if question_id == "gb_synthesis_001":
        return "未同时恢复五类场景和共同合格判据。"
    if question_id == "gb_compare_002":
        return "未恢复载荷比较及异常处理规则。"
    if question_id == "gb_multi_hop_009":
        return "未恢复跨条款的仿真范围和可信度要求。"
    if question_id == "gb_direct_001":
        return "有支持证据但仍选择拒答。"
    return "答案与金标准不一致。"


def manual_rows(questions: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for (variant, mode), codes in LABEL_CODES.items():
        if len(codes) != len(QUESTION_IDS):
            raise RuntimeError(f"Invalid manual code length for {variant}/{mode}")
        for question_id, code in zip(QUESTION_IDS, codes):
            outcome = CODE_TO_OUTCOME[code]
            output.append(
                {
                    "variant": variant,
                    "mode": mode,
                    "question_id": question_id,
                    "task_type": questions[question_id]["task_type"],
                    "outcome": outcome,
                    "score": OUTCOME_SCORE[outcome],
                    "rationale": semantic_rationale(question_id, outcome, variant, mode),
                    "reviewer": "codex_provisional",
                    "review_status": "needs_user_confirmation",
                }
            )
    return output


def manual_summary(rows: list[dict[str, Any]], variant: str, mode: str) -> dict[str, Any]:
    selected = [item for item in rows if item["variant"] == variant and item["mode"] == mode]
    counts = Counter(item["outcome"] for item in selected)
    return {
        "question_count": len(selected),
        "complete_pass_count": counts["pass"],
        "partial_count": counts["partial"],
        "fail_count": counts["fail"],
        "complete_pass_rate": counts["pass"] / len(selected),
        "partial_credit_score": sum(item["score"] for item in selected) / len(selected),
    }


def kg_metrics(variant: str) -> dict[str, float]:
    run = json_file(f"kg_score_{variant}_live.json")["runs"][0]["audit_macro"]
    return {
        key: float(run[key])
        for key in (
            "entity_f1", "type_accuracy", "relation_f1",
            "numeric_tuple_exact_match_f1", "evidence_binding_accuracy",
            "unsupported_node_ratio", "unsupported_edge_ratio",
        )
    }


def pct(value: float | None, digits: int = 1) -> str:
    return "—" if value is None else f"{100 * value:.{digits}f}%"


def number(value: float | None, digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def main() -> None:
    questions = {item["id"]: item for item in load_jsonl(QUESTIONS_PATH)}
    reviews = manual_rows(questions)
    write_jsonl(RESULTS_DIR / "pilot_6q_manual_review.jsonl", reviews)

    automatic = []
    for variant in VARIANTS:
        retrieval = json_file(f"retrieval_score_{variant}_pilot_final.json")
        answers = json_file(f"answer_score_{variant}_pilot_final.json")
        for mode in MODES:
            retrieval_metrics = summary_for(retrieval, mode)
            answer_metrics = summary_for(answers, mode)
            automatic.append(
                {
                    "variant": variant,
                    "mode": mode,
                    "retrieval": {
                        name: mean(retrieval_metrics, name)
                        for name in (
                            "evidence_precision", "evidence_recall", "evidence_f1",
                            "ndcg_at_10", "gold_path_complete",
                            "effective_evidence_per_1000_tokens",
                            "irrelevant_evidence_ratio", "untraceable_item_ratio",
                            "latency_seconds",
                        )
                    },
                    "answer": {
                        name: mean(answer_metrics, name)
                        for name in (
                            "primary_score", "atomic_claim_f1", "citation_correctness",
                            "citation_completeness", "faithfulness",
                            "unanswerable_accuracy", "answer_latency_seconds",
                        )
                    },
                    "manual_semantic": manual_summary(reviews, variant, mode),
                }
            )

    v4_retrieval = json_file("retrieval_score_v4_pilot_final.json")
    v4_answers = json_file("answer_score_v4_pilot_final.json")
    shared = []
    for mode in ("closed_book", "oracle"):
        shared.append(
            {
                "mode": mode,
                "retrieval": {
                    name: mean(summary_for(v4_retrieval, mode), name)
                    for name in ("evidence_recall", "ndcg_at_10", "gold_path_complete")
                },
                "answer": {
                    name: mean(summary_for(v4_answers, mode), name)
                    for name in ("primary_score", "atomic_claim_f1", "citation_correctness", "citation_completeness")
                },
                "manual_semantic": manual_summary(reviews, "shared", mode),
            }
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmark_status": "self_checked_candidate_not_frozen",
        "scope": {
            "question_ids": QUESTION_IDS,
            "variant_count": 4,
            "retrieval_modes": list(MODES),
            "shared_modes": ["closed_book", "oracle"],
            "unique_result_rows": 84,
            "context_budget_tokens": 6000,
            "answer_model_temperature": 0,
            "evidence_mapping_version": "source_exact_hierarchical_clause_v3",
        },
        "automatic_metrics": automatic,
        "shared_baselines": shared,
        "kg_audit_snapshot": {variant: kg_metrics(variant) for variant in VARIANTS},
        "manual_review_file": "pilot_6q_manual_review.jsonl",
        "manual_review_notice": "Codex provisional semantic audit; user confirmation required.",
    }
    write_json(RESULTS_DIR / "pilot_6q_comparison.json", payload)

    lines = [
        "# GB 39901 GraphRAG 六题 Pilot 报告",
        "",
        "> 状态：候选 benchmark（self_checked，尚未 user_reviewed/frozen）。本报告只用于验证评测链路和发现问题，不能替代完整 50 题结论。",
        "",
        "## 运行范围",
        "",
        "- 六题分别覆盖直接事实、条件表格、跨条款多跳、比较例外、跨章节枚举和不可回答。",
        "- A0、v2、v3、v4 均运行 naive、hybrid、mix；闭卷和 oracle 只运行一次并共享。",
        "- 共 84 条有效结果，统一 6000 token 上下文预算、同一阿里云回答模型、temperature=0。",
        "- 发生过一次临时 SSL EOF，runner 从断点有限重试；没有把连接失败计作模型错误。",
        "- Pilot 发现并修复了跨文档同号条款误匹配、条款子串误匹配、父子条款映射、表格 oracle 缺表头和原子声明合并等问题。",
        "",
        "## KG 抽取审计快照",
        "",
        "| 版本 | 实体 F1 | 类型准确率 | 关系 F1 | 数值条件 F1 | 证据绑定 | 无依据节点 | 无依据边 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for variant in VARIANTS:
        kg = payload["kg_audit_snapshot"][variant]
        lines.append(
            f"| {variant.upper()} | {pct(kg['entity_f1'])} | {pct(kg['type_accuracy'])} | "
            f"{pct(kg['relation_f1'])} | {pct(kg['numeric_tuple_exact_match_f1'])} | "
            f"{pct(kg['evidence_binding_accuracy'])} | {pct(kg['unsupported_node_ratio'])} | "
            f"{pct(kg['unsupported_edge_ratio'])} |"
        )

    lines.extend(
        [
            "",
            "## 检索与回答结果",
            "",
            "回答代理分使用确定性结构/词面评分；原子声明相似度阈值为 0.45。oracle 代理分仍未达到 100%，因此只作方向性参考。人工语义列是 Codex 初审，等待用户确认。",
            "",
            "| 版本 | 模式 | 证据召回 | 证据精确 | 证据 F1 | 路径完整 | nDCG@10 | 证据ID噪声 | 不可追溯项 | 回答代理分 | 语义完整通过 | 含部分分 | 检索延迟 | 回答延迟 |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for item in automatic:
        r, a, m = item["retrieval"], item["answer"], item["manual_semantic"]
        lines.append(
            f"| {item['variant'].upper()} | {item['mode']} | {pct(r['evidence_recall'])} | "
            f"{pct(r['evidence_precision'])} | {pct(r['evidence_f1'])} | {pct(r['gold_path_complete'])} | "
            f"{number(r['ndcg_at_10'])} | {pct(r['irrelevant_evidence_ratio'])} | "
            f"{pct(r['untraceable_item_ratio'])} | {pct(a['primary_score'])} | "
            f"{m['complete_pass_count']}/6 | {pct(m['partial_credit_score'])} | "
            f"{number(r['latency_seconds'])}s | {number(a['answer_latency_seconds'])}s |"
        )

    lines.extend(
        [
            "",
            "共享基线：闭卷语义完整通过 1/6；oracle 语义完整通过 6/6。oracle 自动回答代理分为 "
            + pct(shared[1]["answer"]["primary_score"])
            + "，说明当前自动答案评分仍会误罚正确改写。",
            "",
            "## 结论",
            "",
            "1. **图检索确实提高了覆盖率，但没有稳定提高最终回答。** v2/v3/v4 的 hybrid 证据召回和路径完整率均为 100%；对应 naive 分别为 58.3%/66.7%、75.0%/83.3%、75.0%/83.3%。但语义完整通过数并未单调提高。",
            "2. **v3 hybrid 是本 pilot 的最佳检索折中。** 它的证据 F1 为 26.9%，高于 v3 naive 的 21.6% 和 v4 hybrid 的 18.9%；但 v3 naive 的最终语义完整通过仍是 5/6，高于 hybrid 的 4/6。",
            "3. **v4 的 KG 更规范，但 KG 分数与 QA 不单调。** v4 关系 F1 为 22.2%、类型准确率 72.0%，均为四版最佳；然而 v4 hybrid 仍在仿真可信度维度和载荷例外题上遗漏关键条件。",
            "4. **图最稳定的收益出现在跨章节完整枚举。** 四个版本中，综合题的 naive 均失败，而 hybrid 均能恢复五类场景及共同判据。",
            "5. **高召回不能保证安全拒答。** v2 在不可回答题上三种模式都虚构了 50 km/h；即使 hybrid/mix 已召回全部金证据，生成端仍错误作答。",
            "6. **A0 图结果不可追溯。** A0 KG 审计的证据绑定率为 0，修正后的图检索证据召回也为 0；即使回答表面正确，也不能证明来自可核验图证据。",
            "",
            "因此，本轮不能声称 GraphRAG 整体优于向量 RAG。更准确的结论是：图能提升复杂问题的证据覆盖，尤其是跨章节枚举；但当前图检索噪声、证据粒度和生成端条件保持能力抵消了部分收益。",
            "",
            "## 典型失败",
            "",
            "- **v4 hybrid / 多跳仿真题**：正确找到 6.5～6.10，但把“可信度维度”答成“可信度评估、确认”，漏掉能力、准确性、正确性、适用性、可用性。",
            "- **v4 hybrid / 比较例外题**：检索包含两组载荷信息，却没有提供或利用异常质量替代规则，最终错误拒答。",
            "- **v2 全模式 / 不可回答题**：把不存在的 N1 80 km/h 阈值答成 50 km/h，是明确幻觉。",
            "- **v2 naive / 表格题**：选中了错误载荷列，把 10 km/h 答成 0 km/h。",
            "- **A0 图模式**：答案引用无法映射到法规条款，缺少可审计证据链。",
            "",
            "## 下一步",
            "",
            "- 先由用户复核这 6 题及语义判定，冻结 pilot 标注。",
            "- 把长条款进一步拆成原子证据子段，避免“命中同一父条款但漏掉关键句”仍被算作完整召回。",
            "- 为 hybrid/mix 加 reranker 或按问题字段压缩上下文，降低 81%～88% 的证据 ID 噪声。",
            "- 对每个配置至少重复 3 次，测检索稳定性；随后再运行完整 50 题 GB 主集。",
            "",
            "## 结果文件",
            "",
            "- `pilot_6q_comparison.json`：汇总指标。",
            "- `pilot_6q_manual_review.jsonl`：逐题 Codex 初审标签及理由。",
            "- `run_{a0,v2,v3,v4}_pilot_final.jsonl`：逐次检索上下文、回答和引用。",
            "- `retrieval_score_*_pilot_final.json` / `answer_score_*_pilot_final.json`：逐题及分组评分。",
        ]
    )
    (RESULTS_DIR / "pilot_6q_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("pilot report written to benchmark/results/pilot_6q_report.md")


if __name__ == "__main__":
    main()
