#!/usr/bin/env python3
"""Generate a concise benchmark report from KG, retrieval, and answer scores."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from benchmark_common import AUDIT_PATH, QUESTIONS_PATH, load_jsonl


def load_json(path: Path | None) -> dict[str, Any] | list[Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path and path.is_file() else None


def fmt(value: Any) -> str:
    return "—" if value is None else f"{float(value):.3f}"


def metric_mean(summary: dict[str, Any], name: str) -> Any:
    return summary.get("metrics", {}).get(name, {}).get("mean")


def overall_summaries(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not payload:
        return {}
    return {
        item["mode"]: item
        for item in payload.get("summaries", [])
        if item.get("task_type") == "__all__"
    }


def parse_labeled_paths(items: list[str]) -> list[tuple[str, Path]]:
    labeled: list[tuple[str, Path]] = []
    for item in items:
        if "=" not in item:
            raise SystemExit("label=path is required for multi-score inputs")
        label, raw_path = item.split("=", 1)
        labeled.append((label, Path(raw_path)))
    return labeled


def append_retrieval_table(
    lines: list[str],
    rows: list[tuple[str, str, dict[str, Any]]],
    *,
    question_count: int | None = None,
) -> None:
    if question_count is not None:
        lines.append(
            f"本节结果覆盖 {question_count} 道唯一问题。"
            + (" 这是链路冒烟/pilot，不是正式总体结论。" if question_count < 50 else "")
        )
        lines.append("")
    lines.extend(
        [
            "| 方案 | 模式 | Evidence P | Evidence R | Evidence F1 | nDCG@10 | 路径完整率 | 有效证据/1000 token | 无关证据比 | 不可追溯比 | 延迟(s) |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for label, mode, metrics in rows:
        lines.append(
            f"| {label} | {mode} | {fmt(metrics.get('evidence_precision'))} | "
            f"{fmt(metrics.get('evidence_recall'))} | {fmt(metrics.get('evidence_f1'))} | "
            f"{fmt(metrics.get('ndcg_at_10'))} | {fmt(metrics.get('gold_path_complete'))} | "
            f"{fmt(metrics.get('effective_evidence_per_1000_tokens'))} | "
            f"{fmt(metrics.get('irrelevant_evidence_ratio'))} | "
            f"{fmt(metrics.get('untraceable_item_ratio'))} | "
            f"{fmt(metrics.get('latency_seconds'))} |"
        )


def append_answer_table(
    lines: list[str],
    rows: list[tuple[str, str, dict[str, Any], dict[str, Any] | None]],
    *,
    question_count: int | None = None,
) -> None:
    if question_count is not None:
        lines.append(
            f"本节结果覆盖 {question_count} 道唯一问题。"
            + (" 少于50题时只视为链路验证/pilot。" if question_count < 50 else "")
        )
        lines.append("")
    lines.extend(
        [
            "| 方案 | 模式 | 主评分 | 语义完整通过 | 含部分分 | 原子声明F1 | 引用正确率 | 引用完整率 | Faithfulness | 拒答准确率 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for label, mode, metrics, manual in rows:
        semantic = "—"
        partial = "—"
        if manual:
            complete = manual.get("complete_pass_count")
            total = manual.get("question_count")
            if complete is not None and total:
                semantic = f"{complete}/{total}"
            if manual.get("partial_credit_score") is not None:
                partial = fmt(manual.get("partial_credit_score"))
        lines.append(
            f"| {label} | {mode} | {fmt(metrics.get('primary_score'))} | {semantic} | {partial} | "
            f"{fmt(metrics.get('atomic_claim_f1'))} | {fmt(metrics.get('citation_correctness'))} | "
            f"{fmt(metrics.get('citation_completeness'))} | {fmt(metrics.get('faithfulness'))} | "
            f"{fmt(metrics.get('unanswerable_accuracy'))} |"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kg-score", action="append", default=[], help="label=path")
    parser.add_argument("--retrieval-score", type=Path, help="single retrieval score JSON")
    parser.add_argument(
        "--retrieval-score-labeled",
        action="append",
        default=[],
        help="label=path for multi-variant retrieval scores",
    )
    parser.add_argument("--answer-score", type=Path, help="single answer score JSON")
    parser.add_argument(
        "--answer-score-labeled",
        action="append",
        default=[],
        help="label=path for multi-variant answer scores",
    )
    parser.add_argument(
        "--pilot-comparison",
        type=Path,
        help="optional pilot_6q_comparison.json with automatic_metrics rows",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    kg_inputs: list[tuple[str, dict[str, Any]]] = []
    for label, path in parse_labeled_paths(args.kg_score):
        payload = load_json(path)
        if payload and isinstance(payload, dict) and payload.get("runs"):
            kg_inputs.append((label, payload["runs"][0]))

    retrieval = load_json(args.retrieval_score)
    answers = load_json(args.answer_score)
    labeled_retrieval = parse_labeled_paths(args.retrieval_score_labeled)
    labeled_answers = parse_labeled_paths(args.answer_score_labeled)
    pilot = load_json(args.pilot_comparison)
    questions = load_jsonl(QUESTIONS_PATH)
    task_counts: dict[str, int] = {}
    for question in questions:
        task_counts[question["task_type"]] = task_counts.get(question["task_type"], 0) + 1

    lines = [
        "# GB 39901 GraphRAG Benchmark 实验报告",
        "",
        "## Benchmark 状态",
        "",
        f"- 问题数：{len(questions)}（dev 12 / test 48）",
        f"- 抽取审计单元：{len(load_jsonl(AUDIT_PATH))}（5个叙述、5个表格）",
        "- 题型配额：" + "；".join(f"{name}={count}" for name, count in task_counts.items()),
        "- 当前问题状态：self_checked；只有审核表全部标记“通过”后才能冻结v1。",
        "",
        "## KG 构建质量",
        "",
    ]
    if kg_inputs:
        all_live = all("_live" in Path(str(report.get("predicted_path", ""))).stem for _, report in kg_inputs)
        lines.extend(
            [
                "| 方案 | 节点 | 边 | Schema valid | 实体F1 | 类型准确率 | 关系F1 | 数值元组F1 | 证据绑定 | 别名归一化 | 无依据节点 | 无依据关系 | 金路径完整率 |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for label, report in kg_inputs:
            macro = report["audit_macro"]
            diagnostics = report["diagnostics"]
            lines.append(
                f"| {label} | {diagnostics['nodes']} | {diagnostics['edges']} | {fmt(diagnostics['schema_valid_rate'])} | {fmt(macro['entity_f1'])} | "
                f"{fmt(macro.get('type_accuracy'))} | {fmt(macro['relation_f1'])} | {fmt(macro['numeric_tuple_exact_match_f1'])} | "
                f"{fmt(macro['evidence_binding_accuracy'])} | {fmt(macro['alias_normalization_accuracy'])} | "
                f"{fmt(macro['unsupported_node_ratio'])} | {fmt(macro['unsupported_edge_ratio'])} | "
                f"{fmt(report['task_graph']['gold_path']['complete_path_recall'])} |"
            )
        lines.extend(
            [
                "",
                "> 实体/关系 Precision 以10个相对完整审计单元为主；任务金图只覆盖问题所需知识，不能把任务金图之外的所有节点直接判为幻觉。",
                (
                    "> 当前表格来自 Neo4j 在线只读导出，包含后处理后的类型与 schema-valid 标记。"
                    if all_live
                    else "> 当前表格来自本地 LightRAG 向量文件的离线导出。离线文件缺少 Neo4j 后处理后的最终实体类型，因此“类型准确率”为缺失值。"
                ),
                "> A0 中9/10审计单元没有证据绑定，只能退化为全图匹配，其低分不应与v2-v4直接作严格显著性比较。",
                "> 当前每个方案只有一个历史图快照，尚不能报告三次独立建图稳定性、建图耗时和成本。正式结论需在人工冻结v1后补跑。",
            ]
        )
    else:
        lines.append("尚未提供KG评分文件。")

    lines.extend(["", "## 检索对比", ""])
    retrieval_rows: list[tuple[str, str, dict[str, Any]]] = []
    retrieval_question_ids: set[str] = set()

    if isinstance(pilot, dict) and pilot.get("automatic_metrics"):
        for item in pilot["automatic_metrics"]:
            retrieval_rows.append(
                (
                    str(item.get("variant", "pilot")).upper(),
                    str(item.get("mode")),
                    dict(item.get("retrieval") or {}),
                )
            )
        retrieval_question_count = 6
        append_retrieval_table(lines, retrieval_rows, question_count=retrieval_question_count)
        lines.extend(
            [
                "",
                "> 上表来自 6 题 pilot 汇总（`pilot_6q_comparison.json`）。A0 的 hybrid/mix 不可追溯比接近 1，"
                "说明图检索结果几乎无法映射到法规证据 ID，不能把低噪声误读为高质量检索。",
            ]
        )
    elif labeled_retrieval:
        for label, path in labeled_retrieval:
            payload = load_json(path)
            if not isinstance(payload, dict):
                continue
            for question_id in {row["question_id"] for row in payload.get("per_question", [])}:
                retrieval_question_ids.add(question_id)
            for mode, summary in overall_summaries(payload).items():
                metrics = {
                    name: metric_mean(summary, name)
                    for name in (
                        "evidence_precision",
                        "evidence_recall",
                        "evidence_f1",
                        "ndcg_at_10",
                        "gold_path_complete",
                        "effective_evidence_per_1000_tokens",
                        "irrelevant_evidence_ratio",
                        "untraceable_item_ratio",
                        "latency_seconds",
                    )
                }
                retrieval_rows.append((label, mode, metrics))
        append_retrieval_table(lines, retrieval_rows, question_count=len(retrieval_question_ids) or None)
    else:
        retrieval_overall = overall_summaries(retrieval if isinstance(retrieval, dict) else None)
        if retrieval_overall and isinstance(retrieval, dict):
            retrieval_question_count = len({row["question_id"] for row in retrieval.get("per_question", [])})
            for mode, summary in retrieval_overall.items():
                metrics = {
                    name: metric_mean(summary, name)
                    for name in (
                        "evidence_precision",
                        "evidence_recall",
                        "evidence_f1",
                        "ndcg_at_10",
                        "gold_path_complete",
                        "effective_evidence_per_1000_tokens",
                        "irrelevant_evidence_ratio",
                        "untraceable_item_ratio",
                        "latency_seconds",
                    )
                }
                retrieval_rows.append(("run", mode, metrics))
            append_retrieval_table(lines, retrieval_rows, question_count=retrieval_question_count)
        else:
            lines.append("尚未运行/query/data对照实验；服务启动后运行benchmark-run-*目标。")

    lines.extend(["", "## 回答质量", ""])
    answer_rows: list[tuple[str, str, dict[str, Any], dict[str, Any] | None]] = []
    answer_question_ids: set[str] = set()

    if isinstance(pilot, dict) and pilot.get("automatic_metrics"):
        for item in pilot["automatic_metrics"]:
            answer_rows.append(
                (
                    str(item.get("variant", "pilot")).upper(),
                    str(item.get("mode")),
                    dict(item.get("answer") or {}),
                    dict(item.get("manual_semantic") or {}) or None,
                )
            )
        append_answer_table(lines, answer_rows, question_count=6)
        lines.extend(
            [
                "",
                "> 语义完整通过来自 pilot 人工/Codex 初审标签，仍需用户确认。自动主评分会低估正确改写。",
            ]
        )
    elif labeled_answers:
        for label, path in labeled_answers:
            payload = load_json(path)
            if not isinstance(payload, dict):
                continue
            for question_id in {row["question_id"] for row in payload.get("per_question", [])}:
                answer_question_ids.add(question_id)
            for mode, summary in overall_summaries(payload).items():
                metrics = {
                    name: metric_mean(summary, name)
                    for name in (
                        "primary_score",
                        "atomic_claim_f1",
                        "citation_correctness",
                        "citation_completeness",
                        "faithfulness",
                        "unanswerable_accuracy",
                    )
                }
                answer_rows.append((label, mode, metrics, None))
        append_answer_table(lines, answer_rows, question_count=len(answer_question_ids) or None)
    else:
        answer_overall = overall_summaries(answers if isinstance(answers, dict) else None)
        if answer_overall and isinstance(answers, dict):
            answer_question_count = len({row["question_id"] for row in answers.get("per_question", [])})
            for mode, summary in answer_overall.items():
                metrics = {
                    name: metric_mean(summary, name)
                    for name in (
                        "primary_score",
                        "atomic_claim_f1",
                        "citation_correctness",
                        "citation_completeness",
                        "faithfulness",
                        "unanswerable_accuracy",
                    )
                }
                answer_rows.append(("run", mode, metrics, None))
            append_answer_table(lines, answer_rows, question_count=answer_question_count)
        else:
            lines.append("尚未运行统一回答模型实验。")

    lines.extend(["", "## 失败案例", ""])
    failures: list[tuple[float, str, str, str, list[str]]] = []
    sources: list[tuple[str, dict[str, Any]]] = []
    if isinstance(retrieval, dict):
        sources.append(("run", retrieval))
    for label, path in labeled_retrieval:
        payload = load_json(path)
        if isinstance(payload, dict):
            sources.append((label, payload))
    for label, payload in sources:
        failures.extend(
            (
                row.get("evidence", {}).get("recall", 0.0),
                row["question_id"],
                label,
                row["mode"],
                row.get("missing_evidence_ids", []),
            )
            for row in payload.get("per_question", [])
            if row.get("mode") in {"hybrid", "mix"} and row.get("evidence", {}).get("recall", 0.0) < 1.0
        )
    if failures:
        for recall, question_id, label, mode, missing in sorted(failures)[:15]:
            lines.append(
                f"- {label} / {question_id} / {mode}：证据召回={recall:.3f}，缺失={', '.join(missing)}"
            )
    elif isinstance(pilot, dict):
        lines.extend(
            [
                "- A0 hybrid/mix：证据几乎不可追溯，图模式不能作为可审计依据。",
                "- v2 不可回答题：在 naive/hybrid/mix 下曾把不存在的 N1 80 km/h 阈值答成 50 km/h。",
                "- v3/v4 hybrid：跨章节综合题检索提升明显，但多跳/比较题仍会丢失关键条件。",
                "- 详见 `benchmark/results/pilot_6q_report.md`。",
            ]
        )
    else:
        lines.append("没有可用的逐题检索结果，或当前结果中未发现图模式证据缺失。")

    lines.extend(
        [
            "",
            "## 当前结论（pilot）",
            "",
            "- 图检索能提高复杂题的证据覆盖与路径完整率，尤其是跨章节枚举。",
            "- 在 6 题 pilot 中，图模式尚未稳定提高最终回答质量；不能声称 GraphRAG 整体优于向量 RAG。",
            "- v3 hybrid 检索折中较好；v4 KG 结构质量最好（关系 F1 / 类型准确率），但 QA 未同步领先。",
            "- 正式总体结论需：人工冻结 v1 + 完整 50 题 GB 主集 +（可选）三次建图稳定性。",
            "",
            "## 结论解释规则",
            "",
            "- 简单事实题上naive接近mix是合理结果，不能据此否定KG。",
            "- 只有在多跳、比较、综合题上，mix/hybrid相对naive的证据召回、路径完整率和最终回答显著提升，才能说明图产生了任务增益。",
            "- oracle与mix的差距主要定位检索上限；oracle本身仍低，说明回答器、题目或评分器需要检查。",
            "- 若图模式没有增益，应结合审计关系F1、路径缺边、无关证据率和上下文密度报告失败原因，不筛选成功样例。",
            "",
            "## 未完成与建议下一步",
            "",
            "1. 用户复核 `benchmark/review/`（60 题）并冻结 benchmark v1。",
            "2. 运行完整 50 题 GB 主集：`make benchmark-run-a0|v2|v3|v4` 与对应 score。",
            "3. 针对 hybrid/mix 高噪声：加 reranker 或按问题字段压缩上下文。",
            "4. 长条款拆成原子证据子段，减少“命中父条款却漏关键句”。",
            "5. 跨文档 10 题需单独的多文档 workspace，勿在 GB-only 图上解释失败。",
            "",
        ]
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"report written {args.output}")


if __name__ == "__main__":
    main()
