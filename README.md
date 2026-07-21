# GB 39901 AEB Regulation GraphRAG Agent

面向 **轻型汽车 AEBS 法规（GB 39901-2025）** 的开源问答 demo：  
在 [LightRAG](https://github.com/HKUDS/LightRAG) 之上做 **多步取证 Agent + 门控作答 + 离线评测**，而不是再实现一套 RAG 引擎。

| 本仓库（应用层） | 依赖（不 vendoring） |
|------------------|----------------------|
| 证据 Agent `harness/` | LightRAG Docker 镜像 **v1.4.16** |
| 入库/关系约束 `lightrag_custom/`、`scripts/` | Neo4j + 你的 LLM / Embedding API |
| 离线 benchmark `benchmark/` | 法规正文（`corpus/` 已提供 prepared 文本） |

> 一句话：**底座用开源 GraphRAG；我做的是法规场景的 Agent 控制、质量护栏与评测。**

架构图 · [docs/architecture.md](docs/architecture.md) · [CONTRIBUTING](CONTRIBUTING.md) · [NOTICE](NOTICE.md) · [LICENSE](LICENSE) (MIT)

---

## 1. 解决什么问题

法规长文 + 大量表格/条款交叉引用时，常见失败模式是：

1. **表被切碎** → 数值答错或丢行  
2. **图检索噪声大** → 证据覆盖上去了，最终答案反而糊  
3. **Agent 空转** → 袋里其实够了，模型仍反复检索同一子问题  
4. **评测不可信** → 金标泄漏进在线路径，分数虚高  

本项目用 **表原子切块（v3）→ 关系契约（v4）→ 取证 Agent + sufficiency 强制收网** 应对上述问题，并诚实报告「图能帮检索，不自动等于更好答案」。

---

## 2. 系统架构

![Architecture](docs/architecture.svg)

```text
法规 Markdown (prepared / index units)
        │
        ▼
 LightRAG 抽取入库 ──► Neo4j（图，本地） + rag_storage v4（向量/KV，可随仓）
        │
        ├──────────► WebUI /query（naive | hybrid | mix）
        │
        └──────────► harness Agent
                      plan → tools → sufficiency 审核 → compose + 数值门控
```

| 层级 | 路径 | 职责 |
|------|------|------|
| 检索底座 | LightRAG 容器 | 建图、向量、HTTP 查询 |
| 定制注入 | `lightrag_custom/` | 抽取 prompt、关系 endpoint 校验 |
| 在线 Agent | `harness/reg_harness/` | 工具循环、袋压缩、审核收网、拒答 |
| 离线评测 | `benchmark/` | 金标、跑数、打分（默认 **不** 注入在线 Agent） |

更细的包结构见 [harness/ARCHITECTURE.md](harness/ARCHITECTURE.md)，控制层规范见 [harness/PROTOCOL.md](harness/PROTOCOL.md)。

---

## 3. 我做了什么（亮点）

适合写进简历 / 面试口述的点：

1. **表感知切块（v3）**  
   23 张表独立成文档 + 叙述单元，避免表头/表体被 token 切碎；表事实回归 **8/8**。

2. **关系契约（v4）**  
   42 类允许关系在 prompt / `schema_guard` / 后处理三处约束；类型非法关系 **106 → 0**。

3. **取证 Agent（非单次 retrieve→拼 prompt）**  
   多步 `graph_search` / `vector_search`、证据袋、compose 与 **数值接地**（答案数字须在袋中出现）。

4. **Sufficiency 审核 + 强制收网**  
   检索后代码侧判断「够不够」；重复检索 / 袋停滞时 **强制 compose**，避免假缺失空转。  
   实测难题「6.11 五类误响应」：约 **10 步空转 → 4 步收网**，答案仍正确。

5. **评测与在线隔离**  
   默认 `catalog_mode=none`，金标不进在线路径；benchmark 离线打分。

**不声称：** GraphRAG 全面碾压向量 RAG；60 题正式榜；多标准生产多库。

---

## 4. 仓库里有什么 / 没有什么

| 在 git 中 | 仅本地 |
|-----------|--------|
| 源码、`config/`、`compose`、非密钥 profile | **`.env`（API Key）** |
| `corpus/prepared`、`index_ready*` | **`data/neo4j`（~500MB）** |
| **最终版** `data/rag_storage/aeb_gb39901_v4_relation_guard/`（~31MB，无 LLM cache） | a0/v2/v3 索引、LLM cache |
| v4 embedding 指纹 `state/embedding_fingerprint.*v4*` | 其它 state 报告 |
| `benchmark/data` + 少量 `*report*.md` | 大批量跑分 jsonl |

**重要：** git 中的 v4 主要是 **向量/KV**。图库仍在 **本机 Neo4j**，需 `make v4-up` 并按需 ingest。  
Embedding 需与指纹一致（当前记录：**dimension=2560**，模型名见 fingerprint 文件）。

---

## 5. 快速开始

需要：Docker、Python 3.10+、OpenAI 兼容的 **Chat + Embedding** API。

### 5.1 离线自检（可不启 LLM）

```bash
git clone <this-repo> && cd <this-repo>
pip install -r requirements.txt
cd harness && pip install -e . && cd ..
cd harness && python3 -m unittest discover -s tests -v
python3 -m reg_harness.cli describe
```

### 5.2 起服务（要 API Key）

```bash
cp .env.example .env
# 编辑 .env：NEO4J_PASSWORD、LLM_*、EMBEDDING_* （切勿提交 .env）

make v4-up    # Neo4j + LightRAG，workspace = aeb_gb39901_v4_relation_guard
```

- WebUI: http://127.0.0.1:9621  
- Neo4j: http://127.0.0.1:7474  

若图为空，按 Makefile 执行 v4 ingest / postprocess（见 §7）。向量侧已有 git 快照时，仍建议确认服务 `WORKSPACE` 与 v4 一致。

### 5.3 问一题（Agent）

```bash
cd harness
python3 -m reg_harness.cli --profile-env .env.gb39901_v4 \
  ask "GB 39901—2025 适用于哪两类汽车？" --max-steps 6
```

难题（五类误响应 + 共同判据）：

```bash
python3 -m reg_harness.cli --profile-env .env.gb39901_v4 \
  ask "完整列出6.11规定的五类误响应场景，并说明所有场景共同的合格判据。" \
  --max-steps 10
```

### 5.4 截图建议

跑通后可把 WebUI / CLI 截图放到 [`docs/screenshots/`](docs/screenshots/)（勿暴露 Key 与内网地址）。

---

## 6. 目录导航

```text
.
├── harness/           # 取证 Agent（主贡献）
├── lightrag_custom/   # sitecustomize + schema_guard + prompts
├── scripts/           # prepare / ingest / probe
├── benchmark/         # 金标数据 + 打分脚本 + 短报告
├── config/            # 领域 / GB 关系 schema YAML
├── corpus/            # prepared + index-ready 单元
├── data/rag_storage/  # 仅 v4 快照（无 neo4j）
├── docs/              # 架构图、截图说明
├── compose.yaml       # Neo4j + LightRAG
└── Makefile           # v2/v3/v4 流水线入口
```

---

## 7. 实验线：A0 → v4（细节）

主结论在 **v4**；A0–v3 为消融对照，完整命令见 Makefile / [PROJECT_STATUS.md](PROJECT_STATUS.md)。

| 标签 | Workspace | 想法 |
|------|-----------|------|
| A0 | `aeb_demo` | 原版 LightRAG 基线 |
| v2 | `aeb_gb39901_v2` | Schema / 中文 prompt 叠加 |
| v3 | `aeb_gb39901_v3_table_chunks` | 46 结构单元，表原子 |
| **v4** | `aeb_gb39901_v4_relation_guard` | + 42 关系 endpoint 契约 |

**v3 表原子（摘要）**

- 23 张 HTML 表各自独立入库；叙述 23 单元；共 46 文档  
- 上传走 `/documents/texts`，大 chunk、零 overlap，失败可重试  

```bash
make v3-doctor && make v3-prepare && make v3-up && make v3-ingest
make v3-postprocess && make v3-test && make v3-fact-qa
```

**v4 关系守护（摘要）**

- Prompt 列出允许关系；`schema_guard` 写图前过滤；后处理再校验  

```bash
make v4-doctor && make v4-prepare && make v4-up && make v4-ingest
make v4-postprocess && make v4-test && make v4-fact-qa
```

本地对比（2026-07-18，结构 / 表事实）：

| 指标 | v3 表感知 | **v4 关系守护** |
|------|----------:|----------------:|
| 结构文档数 | 46 | 46 |
| 类型非法关系 | 106 | **0** |
| 表事实 + 引用 | 8/8 | **8/8** |

**稳定 takeaway**

1. 表切块修好大量数值题。  
2. 关系合法 ≠ 问答自动变强 → 需要 Agent 与门控。  
3. 图模式常提高证据覆盖，噪声会抵消答案收益。

---

## 8. 语料说明

| 来源 | v0.1 角色 |
|------|-----------|
| **GB 39901-2025** | **唯一主动知识库** |
| UN R152 / Euro NCAP 等 | 可在 `corpus/prepared` 中，**不作为** 主结论 KB |

文本仅供学习研究；**不得**当作型式认证依据。请以正式出版物为准。详见 [NOTICE.md](NOTICE.md)。

---

## 9. 报告与评测入口

| 材料 | 路径 |
|------|------|
| Pilot 6 题报告 | [benchmark/results/pilot_6q_report.md](benchmark/results/pilot_6q_report.md) |
| 汇总报告 | [benchmark/results/benchmark_report.md](benchmark/results/benchmark_report.md) |
| 金标数据 | `benchmark/data/*.jsonl` |
| 评测脚本 | `benchmark/scripts/` |

全量跑分产物默认 gitignore；需要时本地重跑。

---

## 10. 安全

- 只提交 `.env.example` 与无密钥的 `.env.gb39901*`  
- 禁止提交 API Key、Neo4j 数据卷、非 v4 大索引  
- 危险重置（会清索引，需显式确认）：

```bash
make reset-index CONFIRM=RESET_AEB_INDEX
```

---

## 11. 边界（请先读）

这是 **GraphRAG 基线 + 取证 Agent demo**，不是完整汽车本体库，也不是法规规则引擎。  
回答可能出错；涉及合规请核对 **官方标准文本**。

状态总表：[PROJECT_STATUS.md](PROJECT_STATUS.md) · 交付口径：[DELIVERY.md](DELIVERY.md)

---

## 12. English summary

Open-source **application layer** for AEBS regulation QA (GB 39901-2025) on top of LightRAG: multi-step evidence agent, table-aware indexing, relation-endpoint guards, numeric grounding, and a code-side **sufficiency audit** that stops retrieval spin. LightRAG is a Docker dependency (not vendored). Final vector/KV snapshot for workspace `aeb_gb39901_v4_relation_guard` is in-repo; Neo4j remains local. See architecture diagram above and `CONTRIBUTING.md` for setup/tests.
