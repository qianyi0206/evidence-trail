#!/usr/bin/env python3
"""Generate a concise benchmark report from KG, retrieval, and answer scores."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from benchmark_common import (
    AUDIT_PATH,
    EVIDENCE_PATH,
    QUESTIONS_PATH,
    benchmark_data_manifest,
    canonical_json_sha256,
    load_jsonl,
)

RUN_FORMAT_VERSION = 2


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


def require_current_score(payload: Any, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SystemExit(f"{label} is not a score object")
    manifest = payload.get("run_manifest")
    if not isinstance(manifest, dict) or manifest.get("format_version") != RUN_FORMAT_VERSION:
        raise SystemExit(
            f"{label} uses a legacy or missing run_manifest; rerun the v2 scorer "
            "instead of mixing archived metrics into a current report"
        )
    fingerprint = manifest.get("fingerprint")
    calculated = canonical_json_sha256(
        {key: value for key, value in manifest.items() if key != "fingerprint"}
    )
    if fingerprint != calculated:
        raise SystemExit(f"{label} contains a tampered run_manifest")
    if manifest.get("benchmark") != benchmark_data_manifest():
        raise SystemExit(
            f"{label} was scored against different benchmark data; rerun it"
        )
    return payload


def require_current_kg_score(payload: Any, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict) or not payload.get("runs"):
        raise SystemExit(f"{label} is not a KG score object")
    manifest = payload.get("benchmark_manifest")
    if not isinstance(manifest, dict) or manifest != benchmark_data_manifest():
        raise SystemExit(
            f"{label} uses a legacy or different benchmark; rerun score_kg.py"
        )
    return payload


def scoring_note(label: str, payload: dict[str, Any]) -> str:
    config = payload.get("scoring_config") or {}
    parts = []
    if config.get("claim_threshold") is not None:
        parts.append(f"原子声明阈值={float(config['claim_threshold']):g}")
    if config.get("bootstrap_samples") is not None:
        parts.append(f"配对 bootstrap={int(config['bootstrap_samples'])} 次")
    if config.get("paired_baseline"):
        parts.append(f"基线={config['paired_baseline']}")
    return f"> {label} 评分配置：" + ("；".join(parts) if parts else "未记录")


def parse_labeled_paths(items: list[str]) -> list[tuple[str, Path]]:
    labeled: list[tuple[str, Path]] = []
    for item in items:
        if "=" not in item:
            raise SystemExit("label=path is required for multi-score inputs")
        label, raw_path = item.split("=", 1)
        labeled.append((label, Path(raw_path)))
    return labeled


def available_labeled_paths(
    labeled: list[tuple[str, Path]],
) -> tuple[list[tuple[str, Path]], list[tuple[str, Path]]]:
    available = [(label, path) for label, path in labeled if path.is_file()]
    missing = [(label, path) for label, path in labeled if not path.is_file()]
    return available, missing


_VARIANT_RUN_CONFIG_KEYS = {
    "profile_env",
    "profile_sha256",
    "resolved_workspace",
    "index_identity",
}


def score_comparison_signature(payload: dict[str, Any]) -> dict[str, Any]:
    """Return run/scorer fields that must match for a horizontal comparison."""
    manifest = payload["run_manifest"]
    configuration = manifest.get("configuration")
    comparable_configuration = (
        {
            key: value
            for key, value in configuration.items()
            if key not in _VARIANT_RUN_CONFIG_KEYS
        }
        if isinstance(configuration, dict)
        else configuration
    )
    return {
        "runner": manifest.get("runner"),
        "selected_question_ids": sorted(manifest.get("selected_question_ids") or []),
        "modes": sorted(manifest.get("modes") or []),
        "configuration": comparable_configuration,
        "code": manifest.get("code"),
        "scoring_config": payload.get("scoring_config"),
    }


def require_comparable_labeled_scores(
    labeled_payloads: list[tuple[str, dict[str, Any]]],
    *,
    score_kind: str,
) -> None:
    if len(labeled_payloads) < 2:
        return
    baseline_label, baseline_payload = labeled_payloads[0]
    baseline = score_comparison_signature(baseline_payload)
    for label, payload in labeled_payloads[1:]:
        candidate = score_comparison_signature(payload)
        differences = [
            field for field, expected in baseline.items() if candidate.get(field) != expected
        ]
        if differences:
            raise SystemExit(
                f"{score_kind} scores {baseline_label!r} and {label!r} are not "
                "comparable; mismatched fields: "
                + ", ".join(differences)
            )


def require_matching_labeled_runs(
    retrieval_payloads: list[tuple[str, dict[str, Any]]],
    answer_payloads: list[tuple[str, dict[str, Any]]],
) -> None:
    retrieval_by_label = dict(retrieval_payloads)
    answer_by_label = dict(answer_payloads)
    for label in sorted(retrieval_by_label.keys() & answer_by_label.keys()):
        retrieval_fingerprint = retrieval_by_label[label]["run_manifest"].get(
            "fingerprint"
        )
        answer_fingerprint = answer_by_label[label]["run_manifest"].get("fingerprint")
        if retrieval_fingerprint != answer_fingerprint:
            raise SystemExit(
                f"retrieval and answer scores for {label!r} come from different runs"
            )


def append_retrieval_table(
    lines: list[str],
    rows: list[tuple[str, str, dict[str, Any]]],
    *,
    question_count: int | None = None,
    formal_question_count: int | None = None,
) -> None:
    if question_count is not None:
        lines.append(
            f"本节结果覆盖 {question_count} 道唯一问题。"
            + (
                " 这是链路冒烟/pilot，不是正式总体结论。"
                if formal_question_count is not None
                and question_count < formal_question_count
                else ""
            )
        )
        lines.append("")
    lines.extend(
        [
            "| 方案 | 模式 | Evidence P | Evidence R | Evidence F1 | nDCG@10 | 可评估KG真路径完整率 | 有效证据/1000 token | 无关证据比 | 不可追溯比 | 延迟(s) |",
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
    formal_question_count: int | None = None,
) -> None:
    if question_count is not None:
        lines.append(
            f"本节结果覆盖 {question_count} 道唯一问题。"
            + (
                " 未覆盖当前正式问题范围，只视为链路验证/pilot。"
                if formal_question_count is not None
                and question_count < formal_question_count
                else ""
            )
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
    kg_payloads: list[tuple[str, dict[str, Any]]] = []
    for label, path in parse_labeled_paths(args.kg_score):
        payload = load_json(path)
        if payload is not None:
            current = require_current_kg_score(payload, str(path))
            kg_payloads.append((label, current))
            runs = current["runs"]
            for index, run in enumerate(runs, 1):
                run_label = label if len(runs) == 1 else f"{label}#{index}"
                kg_inputs.append((run_label, run))

    retrieval = load_json(args.retrieval_score)
    answers = load_json(args.answer_score)
    labeled_retrieval_paths, missing_retrieval = available_labeled_paths(
        parse_labeled_paths(args.retrieval_score_labeled)
    )
    labeled_answer_paths, missing_answers = available_labeled_paths(
        parse_labeled_paths(args.answer_score_labeled)
    )
    labeled_retrieval = [
        (label, require_current_score(load_json(path), str(path)))
        for label, path in labeled_retrieval_paths
    ]
    labeled_answers = [
        (label, require_current_score(load_json(path), str(path)))
        for label, path in labeled_answer_paths
    ]
    require_comparable_labeled_scores(
        labeled_retrieval,
        score_kind="retrieval",
    )
    require_comparable_labeled_scores(
        labeled_answers,
        score_kind="answer",
    )
    require_matching_labeled_runs(labeled_retrieval, labeled_answers)
    pilot = load_json(args.pilot_comparison)
    if retrieval is not None:
        retrieval = require_current_score(retrieval, str(args.retrieval_score))
    if answers is not None:
        answers = require_current_score(answers, str(args.answer_score))
    pilot_is_current = (
        isinstance(pilot, dict)
        and pilot.get("scoring_contract_version") == "v2"
        and bool(pilot.get("automatic_metrics"))
    )
    questions = load_jsonl(QUESTIONS_PATH)
    evidence = load_jsonl(EVIDENCE_PATH)
    audit_units = load_jsonl(AUDIT_PATH)
    split_counts: dict[str, int] = {}
    source_counts = {
        "gb": sum(item["id"].startswith("gb_") for item in questions),
        "cross": sum(item["id"].startswith("cross_") for item in questions),
    }
    for question in questions:
        split_counts[question["split"]] = split_counts.get(question["split"], 0) + 1
    audit_kinds: dict[str, int] = {}
    for unit in audit_units:
        audit_kinds[unit["kind"]] = audit_kinds.get(unit["kind"], 0) + 1
    task_counts: dict[str, int] = {}
    for question in questions:
        task_counts[question["task_type"]] = task_counts.get(question["task_type"], 0) + 1

    lines = [
        "# GB 39901 GraphRAG Benchmark 实验报告",
        "",
        "## Benchmark 状态",
        "",
        f"- 问题数：{len(questions)}（dev {split_counts.get('dev', 0)} / test {split_counts.get('test', 0)}；GB {source_counts['gb']} / cross {source_counts['cross']}）",
        f"- 证据记录：{len(evidence)}；来源文档：{len({item['source_file'] for item in evidence})}",
        f"- 抽取审计单元：{len(audit_units)}（叙述 {audit_kinds.get('narrative', 0)} / 表格 {audit_kinds.get('table', 0)}）",
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
                f"> 实体/关系 Precision 以{len(audit_units)}个相对完整审计单元为主；任务金图只覆盖问题所需知识，不能把任务金图之外的所有节点直接判为幻觉。",
                (
                    "> 当前表格来自 Neo4j 在线只读导出，包含后处理后的类型与 schema-valid 标记。"
                    if all_live
                    else "> 当前表格来自本地 LightRAG 向量文件的离线导出。离线文件缺少 Neo4j 后处理后的最终实体类型，因此“类型准确率”为缺失值。"
                ),
            ]
        )
        for label, report in kg_inputs:
            unscoped = sum(
                row.get("scope_method") == "no_evidence_binding"
                for row in report.get("audit_units", [])
            )
            if unscoped:
                lines.append(
                    f"> {label} 有 {unscoped}/{len(report.get('audit_units', []))} "
                    "个审计单元没有可归属预测，按空预测计分。"
                )
        for label, payload in kg_payloads:
            stability = payload.get("stability") or {}
            if stability.get("available"):
                lines.append(
                    f"> {label} 独立建图 {stability.get('run_count')} 次："
                    f"实体 Jaccard={fmt(stability.get('mean_entity_jaccard'))}，"
                    f"边 Jaccard={fmt(stability.get('mean_edge_jaccard'))}，"
                    f"实体 F1 标准差={fmt(stability.get('audit_entity_f1_stddev'))}，"
                    f"关系 F1 标准差={fmt(stability.get('audit_relation_f1_stddev'))}。"
                )
            else:
                lines.append(
                    f"> {label} 只有 {stability.get('run_count', len(payload.get('runs', [])))} "
                    "个图快照，尚不能报告独立建图稳定性。"
                )
            efficiency = payload.get("build_efficiency") or {}
            if efficiency.get("available"):
                lines.append(
                    f"> {label} 建图耗时均值={fmt(efficiency.get('mean_elapsed_seconds'))} s，"
                    f"成本均值={fmt(efficiency.get('mean_cost_usd'))} USD，"
                    f"成本合计={fmt(efficiency.get('total_cost_usd'))} USD。"
                )
    else:
        lines.append("尚未提供KG评分文件。")

    lines.extend(["", "## 检索对比", ""])
    retrieval_rows: list[tuple[str, str, dict[str, Any]]] = []
    retrieval_question_ids: set[str] = set()

    if pilot_is_current and isinstance(pilot, dict):
        for item in pilot["automatic_metrics"]:
            retrieval_rows.append(
                (
                    str(item.get("variant", "pilot")).upper(),
                    str(item.get("mode")),
                    dict(item.get("retrieval") or {}),
                )
            )
        retrieval_question_count = (
            len(pilot.get("scope", {}).get("question_ids", [])) or None
        )
        append_retrieval_table(
            lines,
            retrieval_rows,
            question_count=retrieval_question_count,
            formal_question_count=source_counts["gb"],
        )
        lines.extend(
            [
                "",
                f"> 上表来自 {retrieval_question_count or '未知数量'} 题 pilot 汇总（`pilot_6q_comparison.json`）。A0 的 hybrid/mix 不可追溯比接近 1，"
                "说明图检索结果几乎无法映射到法规证据 ID，不能把低噪声误读为高质量检索。",
                "> 若该 pilot 文件没有 v2 run_manifest，它属于旧评分契约归档，只能用于历史排障，必须重跑后才能与新版真图路径/拒答指标比较。",
            ]
        )
    elif labeled_retrieval:
        for label, payload in labeled_retrieval:
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
        append_retrieval_table(
            lines,
            retrieval_rows,
            question_count=len(retrieval_question_ids) or None,
            formal_question_count=source_counts["gb"],
        )
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
            append_retrieval_table(
                lines,
                retrieval_rows,
                question_count=retrieval_question_count,
                formal_question_count=source_counts["gb"],
            )
        else:
            lines.append("尚未运行/query/data对照实验；服务启动后运行benchmark-run-*目标。")
    if missing_retrieval:
        lines.append(
            "> 尚未找到当前检索评分："
            + "、".join(f"{label} (`{path}`)" for label, path in missing_retrieval)
            + "；完成对应 benchmark-run-* 后运行 benchmark-score-*。"
        )
    if isinstance(pilot, dict) and pilot.get("automatic_metrics") and not pilot_is_current:
        lines.extend(
            [
                "",
                "> 已提供的 pilot 汇总属于旧评分契约归档，未载入当前指标表；请用 v2 runner/scorer 重跑后再生成报告。",
            ]
        )
    if isinstance(retrieval, dict):
        lines.append(scoring_note("检索", retrieval))
    for label, payload in labeled_retrieval:
        lines.append(scoring_note(f"检索 {label}", payload))

    lines.extend(["", "## 回答质量", ""])
    answer_rows: list[tuple[str, str, dict[str, Any], dict[str, Any] | None]] = []
    answer_question_ids: set[str] = set()

    if pilot_is_current and isinstance(pilot, dict):
        for item in pilot["automatic_metrics"]:
            answer_rows.append(
                (
                    str(item.get("variant", "pilot")).upper(),
                    str(item.get("mode")),
                    dict(item.get("answer") or {}),
                    dict(item.get("manual_semantic") or {}) or None,
                )
            )
        pilot_question_count = len(
            pilot.get("scope", {}).get("question_ids", [])
        ) or None
        append_answer_table(
            lines,
            answer_rows,
            question_count=pilot_question_count,
            formal_question_count=source_counts["gb"],
        )
        lines.extend(
            [
                "",
                "> 语义完整通过来自 pilot 人工/Codex 初审标签，仍需用户确认。自动主评分会低估正确改写。",
            ]
        )
    elif labeled_answers:
        for label, payload in labeled_answers:
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
        append_answer_table(
            lines,
            answer_rows,
            question_count=len(answer_question_ids) or None,
            formal_question_count=source_counts["gb"],
        )
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
            append_answer_table(
                lines,
                answer_rows,
                question_count=answer_question_count,
                formal_question_count=source_counts["gb"],
            )
        else:
            lines.append("尚未运行统一回答模型实验。")
    if missing_answers:
        lines.append(
            "> 尚未找到当前回答评分："
            + "、".join(f"{label} (`{path}`)" for label, path in missing_answers)
            + "；完成对应 benchmark-run-* 后运行 benchmark-score-*。"
        )
    if isinstance(answers, dict):
        lines.append(scoring_note("回答", answers))
    for label, payload in labeled_answers:
        lines.append(scoring_note(f"回答 {label}", payload))

    lines.extend(["", "## 失败案例", ""])
    failures: list[tuple[float, str, str, str, list[str]]] = []
    sources: list[tuple[str, dict[str, Any]]] = []
    if isinstance(retrieval, dict):
        sources.append(("run", retrieval))
    for label, payload in labeled_retrieval:
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
    elif pilot_is_current and isinstance(pilot, dict):
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
            "## 当前可报告结论",
            "",
            "- 只根据本报告实际加载的当前 scorer 输出作结论；缺少结果时不沿用历史 pilot 数值。",
            "- `gold_path_complete` 现在只统计 Schema 合法且来源匹配的真实图边连通路径；旧版按 evidence ID 交集计算的结果不可直接比较。",
            "- 模式差异应优先读取评分 JSON 的 paired bootstrap delta 与置信区间，而不是比较两条独立均值区间。",
            f"- 正式总体结论需：人工冻结 v1 + 完整 {source_counts['gb']} 题 GB 主集 + 至少三次独立建图稳定性。",
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
            f"1. 用户复核 `benchmark/review/`（{len(questions)} 题）并冻结 benchmark v1。",
            f"2. 运行完整 {source_counts['gb']} 题 GB 主集：`make benchmark-run-a0|v2|v3|v4` 与对应 score。",
            "3. 针对 hybrid/mix 高噪声：加 reranker 或按问题字段压缩上下文。",
            "4. 长条款拆成原子证据子段，减少“命中父条款却漏关键句”。",
            f"5. 跨文档 {source_counts['cross']} 题需单独的多文档 workspace，勿在 GB-only 图上解释失败。",
            "",
        ]
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"report written {args.output}")


if __name__ == "__main__":
    main()
