# GB 39901 GraphRAG Benchmark 实验报告

## Benchmark 状态

- 问题数：60（dev 12 / test 48；GB 50 / cross 10）
- 证据记录：63；来源文档：4
- 抽取审计单元：10（叙述 5 / 表格 5）
- 题型配额：direct_fact=8；conditional_table=10；multi_hop_relation=12；comparison_exception=8；cross_section_synthesis=6；unanswerable_adversarial=6；cross_document_alignment=4；cross_document_comparison=3；cross_document_synthesis=2；cross_document_unanswerable=1
- 当前问题状态：self_checked；只有审核表全部标记“通过”后才能冻结v1。

## KG 构建质量

尚未提供KG评分文件。

## 检索对比

尚未运行/query/data对照实验；服务启动后运行benchmark-run-*目标。

## 回答质量

尚未运行统一回答模型实验。

## 失败案例

没有可用的逐题检索结果，或当前结果中未发现图模式证据缺失。

## 当前可报告结论

- 只根据本报告实际加载的当前 scorer 输出作结论；缺少结果时不沿用历史 pilot 数值。
- `gold_path_complete` 现在只统计 Schema 合法且来源匹配的真实图边连通路径；旧版按 evidence ID 交集计算的结果不可直接比较。
- 模式差异应优先读取评分 JSON 的 paired bootstrap delta 与置信区间，而不是比较两条独立均值区间。
- 正式总体结论需：人工冻结 v1 + 完整 50 题 GB 主集 + 至少三次独立建图稳定性。

## 结论解释规则

- 简单事实题上naive接近mix是合理结果，不能据此否定KG。
- 只有在多跳、比较、综合题上，mix/hybrid相对naive的证据召回、路径完整率和最终回答显著提升，才能说明图产生了任务增益。
- oracle与mix的差距主要定位检索上限；oracle本身仍低，说明回答器、题目或评分器需要检查。
- 若图模式没有增益，应结合审计关系F1、路径缺边、无关证据率和上下文密度报告失败原因，不筛选成功样例。

## 未完成与建议下一步

1. 用户复核 `benchmark/review/`（60 题）并冻结 benchmark v1。
2. 运行完整 50 题 GB 主集：`make benchmark-run-a0|v2|v3|v4` 与对应 score。
3. 针对 hybrid/mix 高噪声：加 reranker 或按问题字段压缩上下文。
4. 长条款拆成原子证据子段，减少“命中父条款却漏关键句”。
5. 跨文档 10 题需单独的多文档 workspace，勿在 GB-only 图上解释失败。
