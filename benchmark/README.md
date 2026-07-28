# GB 39901 GraphRAG Benchmark

本目录是一套可审计的候选 benchmark。它把“图抽取得好不好”“图是否改善检索”以及“整个 GraphRAG 是否改善最终回答”分开评分，避免只用问答正确率反推 KG 质量。

当前版本包含 60 题：50 题 GB 39901 主集和 10 题跨文档外测；12 题属于 dev，48 题属于 test。所有题目当前均为 `self_checked`，尚未经过用户法规复核，因此不能称为冻结的 v1。

## 目录

- `data/evidence.jsonl`：63 条带来源 SHA-256 的条款、表格或表格行证据。
- `data/questions.jsonl`：问题、结构化答案、原子声明、证据、金节点、金边和金路径。
- `data/task_graph.jsonl`：显式区分 `reasoning` 任务推理图与 `extractable_kg` 抽取审计图。
- `data/audit_units.jsonl`：5 个叙述单元、5 个表格单元。
- `review/benchmark_review.csv`：人工复核入口。
- `schema/benchmark.schema.json`：问题数据契约。
- `scripts/`：构建、校验、冻结、实验、评分和报告脚本。
- `results/`：离线 KG 导出、逐题运行结果和汇总报告。

## 数据配额

GB 主集严格包含：直接事实 8、表格多条件 10、多跳关系 12、比较/例外/实施 8、跨章节综合 6、不可回答 6。跨文档外测包含：法规映射 4、协议比较 3、三层综合 2、证据不足 1。

每题的 `self_review` 六项检查必须全部为 `true`；每个原子声明必须绑定证据；每条金路径中的节点、边和证据必须存在。6 道已发布 pilot 题固定在 dev，避免用公开调试样例污染 test。机械校验会实际执行 `benchmark.schema.json`，并检查题型配额、dev/test 划分、审计单元平衡、来源文件哈希、推理路径连通性，以及 `gold_kg_path` 是否满足 GB v4 YAML 的关系端点约束并与来源一致。

## 构建与机械校验

这些步骤不需要 Docker 或模型 API；校验器复用项目已有的 PyYAML 读取 GB v4 契约，其余逻辑为仓库内实现：

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

每份 metadata 至少记录 `run_id`、`elapsed_seconds` 和 `cost_usd`；可额外保留输入/输出 token。评分器会输出实体/边 Jaccard、审计 F1 标准差、平均耗时及平均/总成本，并把当前 benchmark manifest 与预测图哈希写入评分文件；报告器拒绝载入旧数据契约生成的 KG 分数。

## 人工复核与冻结

优先打开 `review/outputs/019f7557-b5c5-72e2-a64a-17612120443a/GB39901_GraphRAG_Benchmark_Review.xlsx`。工作簿包含审核说明、逐题审核和证据索引三张表，并为审核决定提供下拉选项。`review/benchmark_review.csv` 是冻结脚本的机器入口；完成 XLSX 复核后由 Codex 把决定同步回 CSV。

逐题阅读问题、答案、原子声明、定位、规范化事实、证据原文和金路径，然后在 `review_decision` 中填写。审核 CSV 同时保存问题及其引用证据/图记录的内容哈希；数据变化后旧审核决定会被判定为过期，不能静默沿用：

- `通过`：法规语义、条件和答案均准确。
- `修改`：在 `review_notes` 写明应修改的内容；修改数据并重新生成审核表后再次复核。
- `删除`：说明歧义、证据不足或不适合作为 benchmark 的原因；删除后需补充同题型问题以保持配额。

冻结脚本只有在 60 行均为 `通过`、ID 集完全一致且内容哈希仍匹配时，才会创建不可覆盖的发布目录及 checksum manifest：

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

每个 `benchmark-run-*` 默认只跑 50 题 GB 主集，并对 `closed_book`、`naive`、`hybrid`、`mix`、`oracle` 使用同一个回答模型和 6000-token 上下文预算。`closed_book` 允许模型只依赖参数知识但禁止伪造引用；其余模式只能根据提供的上下文作答。运行器调用 LightRAG `/query/data`，把检索与生成分离，并在每题每模式后增量写盘。

每次运行都写入不可变 `run_manifest`、运行 ID 和指纹，绑定 benchmark 数据、代码、配置、题目集合、模式以及实际检索索引身份。默认索引身份来自解析后的 workspace 对应的 `state/embedding_fingerprint.<workspace>.json`：文件必须使用 schema v2 且状态为 `ready`，manifest 会绑定 workspace、embedding 配置/哈希以及 corpus、bundle、source 或 prepared-document 哈希。`recorded_at`、备注等非语义元数据不参与身份计算。

索引指纹缺失、非 `ready`、内容自相矛盾或 workspace 不匹配时，runner 会 fail closed；`--resume` 也只接受完全相同的 manifest。评分器拒绝旧格式、混合运行、重复 `(question_id, mode)` 以及 manifest 之外的记录。改变 split、limit、模式、模型、上下文预算、代码或索引后，必须使用新的输出文件重新运行。

仓库目前只提交了 v4 workspace 的可信 `ready` 指纹。A0、v2、v3 的 `make benchmark-run-*` 会在各自 workspace 完成 verified ingest、生成对应状态文件之前明确拒绝运行；不得借用 v4 指纹或伪造状态来绕过。

若要报告回答调用成本，应同时传入 `--input-cost-per-million` 和 `--output-cost-per-million`。没有可靠价格或 LightRAG 未返回检索成本时，结果写为 `null`，不会误报成零成本。

10 题跨文档集不能在当前仅含 GB 的四个 workspace 上做有效比较。必须先建立包含 GB、UNECE R152、Euro NCAP C2C 和评分协议的独立多文档外测 workspace，再显式运行：

```bash
python3 benchmark/scripts/run_graphrag_benchmark.py \
  --source-set cross --profile-env <multi-document-profile> \
  --index-fingerprint <immutable-index-build-id> \
  --output benchmark/results/run_cross.jsonl --resume
```

`--index-fingerprint` 是远程/跨文档索引的显式责任边界，只能填写能唯一标识一次不可变索引构建的 ID；索引重建后必须更换 ID。可读取本地状态文件时不要使用该参数绕过校验。

正式大规模运行前可在 tools 容器中用 `--split dev --limit 1 --retrieval-only` 冒烟。不要把跨文档题在 GB-only workspace 上的失败解释为图方法本身失败。

## 指标解释

KG 以 10 个相对完整审计单元计算实体、方向敏感关系、数值—单位—条件元组、证据绑定、别名归一化和无依据比例。审计使用 `extractable_kg` 图；问答中的 `reasoning` 图只表达推理依赖，不能直接当作可从原文抽取的 KG。KG 路径评分只使用 Schema 合法、来源匹配且完整连通的 `gold_kg_path`，也不能把任务金图之外的节点一律判为幻觉。

检索评分包括 Evidence P/R/F1、nDCG@10、真实图路径边召回/完整率、推理路径证据支持率、有效证据密度、无关证据率和延迟。真实图路径必须逐边一对一匹配端点与关系并形成连通链，不能再用 evidence ID 交集冒充。若一个宽泛检索项映射到多个 evidence ID，其 token 按命中的金证据 ID 占比分摊，避免只包含一小段金条款却把整块上下文计为有效。

回答评分包括结构化 EM、字段准确率、集合 F1、原子声明 F1、引用正确/完整率、基于已呈现上下文的 faithfulness 代理指标和拒答准确率。执行错误、超时和空结果不计为正确拒答；声明匹配会拒绝否定、比较符、数值和单位冲突。模式差异使用同题配对 bootstrap 95% 置信区间，评分 JSON 会保留实际阈值与 bootstrap 配置。

只有复杂题上 `hybrid`/`mix` 相对 `naive` 同时改善证据召回、路径完整率和最终答案，才能声称 KG 带来任务增益。简单事实题持平是合理控制结果；若无增益，应如实结合关系缺边、证据绑定失败和无关上下文解释。
