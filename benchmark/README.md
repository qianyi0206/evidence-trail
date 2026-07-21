# GB 39901 GraphRAG Benchmark

本目录是一套可审计的候选 benchmark。它把“图抽取得好不好”“图是否改善检索”以及“整个 GraphRAG 是否改善最终回答”分开评分，避免只用问答正确率反推 KG 质量。

当前版本包含 60 题：50 题 GB 39901 主集和 10 题跨文档外测；12 题属于 dev，48 题属于 test。所有题目当前均为 `self_checked`，尚未经过用户法规复核，因此不能称为冻结的 v1。

## 目录

- `data/evidence.jsonl`：61 条带来源 SHA-256 的条款或表格行证据。
- `data/questions.jsonl`：问题、结构化答案、原子声明、证据、金节点、金边和金路径。
- `data/task_graph.jsonl`：任务金图和抽取审计金图。
- `data/audit_units.jsonl`：5 个叙述单元、5 个表格单元。
- `review/benchmark_review.csv`：人工复核入口。
- `schema/benchmark.schema.json`：问题数据契约。
- `scripts/`：构建、校验、冻结、实验、评分和报告脚本。
- `results/`：离线 KG 导出、逐题运行结果和汇总报告。

## 数据配额

GB 主集严格包含：直接事实 8、表格多条件 10、多跳关系 12、比较/例外/实施 8、跨章节综合 6、不可回答 6。跨文档外测包含：法规映射 4、协议比较 3、三层综合 2、证据不足 1。

每题的 `self_review` 六项检查必须全部为 `true`；每个原子声明必须绑定证据；每条金路径中的节点、边和证据必须存在。机械校验还会检查题型配额、dev/test 划分、审计单元平衡、来源文件哈希和审计图 schema。

## 构建与机械校验

这些步骤只使用 Python 标准库，不需要 Docker 或模型 API：

```bash
cd /Users/qianyi/project/car_project/demo/aeb
make benchmark-build
make benchmark-validate
make benchmark-test
make benchmark-kg-offline
make benchmark-report
```

`benchmark-kg-offline` 从四个已经存在的 LightRAG 本地工作区导出 A0、v2、v3、v4 图快照并评分。离线向量存储没有 Neo4j 后处理后的最终类型元数据，因此实体类型、关系类型和证据绑定结果应视为诊断值。

Docker/Neo4j 可用时运行 `make benchmark-kg-live`，按 workspace 标签只读导出类型化在线图。`make benchmark-report` 默认使用该在线导出；正式 KG 结论仍应在冻结 v1 后补充三次独立建图稳定性、耗时和成本。

三次独立建图应使用不同的新 workspace，分别导出后把三个图和三份运行元数据一起交给评分器：

```bash
python3 benchmark/scripts/score_kg.py \
  --predicted run1.jsonl --predicted run2.jsonl --predicted run3.jsonl \
  --run-metadata run1.meta.json --run-metadata run2.meta.json --run-metadata run3.meta.json \
  --output stability_score.json
```

每份 metadata 至少记录 `run_id`、`elapsed_seconds` 和 `cost_usd`；可额外保留输入/输出 token。评分器会输出实体/边 Jaccard、审计 F1 标准差、平均耗时及平均/总成本。

## 人工复核与冻结

优先打开 `review/outputs/019f7557-b5c5-72e2-a64a-17612120443a/GB39901_GraphRAG_Benchmark_Review.xlsx`。工作簿包含审核说明、逐题审核和证据索引三张表，并为审核决定提供下拉选项。`review/benchmark_review.csv` 是冻结脚本的机器入口；完成 XLSX 复核后由 Codex 把决定同步回 CSV。

逐题阅读问题、答案、原子声明、定位、规范化事实、证据原文和金路径，然后在 `review_decision` 中填写：

- `通过`：法规语义、条件和答案均准确。
- `修改`：在 `review_notes` 写明应修改的内容；修改数据并重新生成审核表后再次复核。
- `删除`：说明歧义、证据不足或不适合作为 benchmark 的原因；删除后需补充同题型问题以保持配额。

冻结脚本只有在 60 行均为 `通过` 时才会创建不可覆盖的发布目录及 checksum manifest：

```bash
python3 benchmark/scripts/freeze_benchmark.py --version v1
```

在复核前不要批量填写“通过”。法规 benchmark 的最终金标准仍需要人确认；模型和机械校验只能减少而不能消除语义错误。

## 正式 GraphRAG 实验

Docker Desktop、模型端点和对应 workspace 可用后，分别运行：

```bash
make benchmark-run-a0
make benchmark-run-v2
make benchmark-run-v3
make benchmark-run-v4

make benchmark-score-a0
make benchmark-score-v2
make benchmark-score-v3
make benchmark-score-v4
```

每个 `benchmark-run-*` 默认只跑 50 题 GB 主集，并对 `closed_book`、`naive`、`hybrid`、`mix`、`oracle` 使用同一个回答模型和 6000-token 上下文预算。`closed_book` 允许模型只依赖参数知识但禁止伪造引用；其余模式只能根据提供的上下文作答。运行器调用 LightRAG `/query/data`，把检索与生成分离，并在每题每模式后增量写盘；`--resume` 可从中断位置继续。

若要报告回答调用成本，应同时传入 `--input-cost-per-million` 和 `--output-cost-per-million`。没有可靠价格或 LightRAG 未返回检索成本时，结果写为 `null`，不会误报成零成本。

10 题跨文档集不能在当前仅含 GB 的四个 workspace 上做有效比较。必须先建立包含 GB、UNECE R152、Euro NCAP C2C 和评分协议的独立多文档外测 workspace，再显式运行：

```bash
python3 benchmark/scripts/run_graphrag_benchmark.py \
  --source-set cross --profile-env <multi-document-profile> \
  --output benchmark/results/run_cross.jsonl --resume
```

正式大规模运行前可在 tools 容器中用 `--split dev --limit 1 --retrieval-only` 冒烟。不要把跨文档题在 GB-only workspace 上的失败解释为图方法本身失败。

## 指标解释

KG 以 10 个相对完整审计单元计算实体、方向敏感关系、数值—单位—条件元组、证据绑定、别名归一化和无依据比例；任务金图只计算金路径召回，不能把任务金图之外的节点一律判为幻觉。

检索评分包括 Evidence P/R/F1、nDCG@10、金路径完整率、有效证据密度、无关证据率和延迟。若一个宽泛检索项映射到多个 evidence ID，其 token 按命中的金证据 ID 占比分摊，避免只包含一小段金条款却把整块上下文计为有效。回答评分包括结构化 EM、字段准确率、集合 F1、原子声明 F1、引用正确/完整率、基于金声明和金证据的 faithfulness 代理指标、拒答准确率及 bootstrap 95% 置信区间。

只有复杂题上 `hybrid`/`mix` 相对 `naive` 同时改善证据召回、路径完整率和最终答案，才能声称 KG 带来任务增益。简单事实题持平是合理控制结果；若无增益，应如实结合关系缺边、证据绑定失败和无关上下文解释。
