# 交付说明（v0.1 收紧版）

## 本版范围（固定）

| 项 | 本版 |
|----|------|
| **主知识库** | **仅 GB 39901-2025**（轻型汽车 AEBS） |
| 英文三份（UN R152 / Euro NCAP×2） | 语料可登记，`enabled: false`，**不参与主建图、主问答、主结论** |
| 多库 / 自动合并 / Librarian 真建库 | **架构预留，本版不交付** |
| 完整 50 题 formal 评测 / 冻结 v1 | **不要求**；pilot 与表格回归结果已有 |

## 本版交付了什么

1. **GraphRAG 建图实验（A0→v4）**  
   - 表感知切分（v3）、关系守卫（v4）等并列 workspace  
   - 结论：图可提升复杂题证据覆盖；hybrid/mix 噪声大时答案不稳；v4 图更规范但不等于 QA 全面更好  

2. **法规取证 Agent 框架（`harness/`）**  
   - LightRAG = 建图 + 检索后端  
   - Harness = 意图路由、多步取证、条款/表格精查、门控作答  
   - 多 KB / L0·L1·L2 / Librarian 仅接口与文档预留  

3. **可复核结果锚点**  
   - `benchmark/results/pilot_6q_report.md`  
   - `benchmark/results/benchmark_report.md`  
   - `results/fact_qa_*.json`（表格 8/8）  

## 怎么演示（由浅到深）

### Level 0 — 不调模型（看框架与结论）

```bash
cd demo/aeb/harness
python3 -m unittest discover -s tests -v
python3 -m reg_harness.cli describe
python3 -m reg_harness.cli intent "完整列出6.11规定的五类误响应场景，并说明所有场景共同的合格判据。"
python3 -m reg_harness.cli lookup clause 6.11
python3 -m reg_harness.cli lookup table 2 --vehicle N1 --ego-kmh 40 --load-state 最大设计总质量
```

阅读：`benchmark/results/pilot_6q_report.md`、`PROJECT_STATUS.md`、`harness/ARCHITECTURE.md`。

### Level 1 — 已有索引 + API（可选）

```bash
cd demo/aeb
# 配置 .env（勿提交）；参考 .env.example
make v4-up          # 或 make up / v3-up
cd harness
python3 -m reg_harness.cli ask "GB 39901—2025 适用于哪两类汽车？" --profile-env .env.gb39901_v4
```

WebUI：<http://127.0.0.1:9621>

### Level 2 — 全量重建（重、需 API）

```bash
make configure && # 编辑 .env
make doctor && make download && make prepare && make up && make ingest
# GB 专用：make gb-demo / v3-demo / v4-demo
```

## 安全与开源边界

- **禁止提交** `.env`（含 API Key、Neo4j 密码）及任意真实密钥  
- **可提交**：`data/rag_storage/aeb_gb39901_v4_relation_guard/` 向量/KV 快照（**不含** LLM cache）；prepared / index 语料  
- **勿提交**：Neo4j 数据卷（`data/neo4j/`）、非 v4 workspace、`corpus/raw` 大体量 PDF、LLM response cache、本地 `results/` 中含密钥的产物  
- 配置模板：`.env.example`；细节见根 README §5.1 与 `.gitignore`  


## 诚实结论（可写进简历）

1. 在 GB 39901 上，**表原子切分与关系约束**能改善建图可审计性与读表稳定性。  
2. **图检索常提高证据覆盖，但不自动提高最终答案**；噪声上下文是主要矛盾之一。  
3. 上层应用宜做成 **取证 Agent（精查 + 槽位 + 门控）**，而不是只换 LightRAG 的 query mode。  

## 明确不在本版

- 新增多份中文标准并入库  
- 启用英文三份做主库  
- 自动 schema 设计 / 自动图谱合并  
- 完整 50 题正式跑分与 benchmark v1 冻结  
