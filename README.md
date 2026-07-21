# GB 39901 轻型汽车 AEBS 法规 GraphRAG Agent

面向 **GB 39901-2025（轻型汽车自动紧急制动系统）** 的开源法规问答 demo。

在开源框架 [LightRAG](https://github.com/HKUDS/LightRAG) 之上，实现 **多步取证 Agent、入库与关系约束、数值门控与离线评测**，而不是重新实现一套 RAG 引擎。

| 本仓库负责（应用层） | 外部依赖（不收录其源码） |
|----------------------|--------------------------|
| 取证 Agent（`harness/`） | LightRAG Docker 镜像 **v1.4.16** |
| 入库定制与关系守护（`lightrag_custom/`、`scripts/`） | Neo4j + 你的大模型 / 向量模型 API |
| 离线评测（`benchmark/`） | 法规文本（仓库内已含 prepared 语料） |

> **一句话：** 检索底座用开源 GraphRAG；本项目做的是法规场景的 Agent 控制、质量护栏与评测。

相关文档：

- 架构说明与示意图：[docs/architecture.md](docs/architecture.md)
- 贡献指南：[CONTRIBUTING.md](CONTRIBUTING.md)
- 第三方与法规声明：[NOTICE.md](NOTICE.md)
- 许可证：本仓库 [MIT](LICENSE)（LightRAG 遵循其自身许可证）
- 状态总表：[PROJECT_STATUS.md](PROJECT_STATUS.md) · 交付说明：[DELIVERY.md](DELIVERY.md)

---

## 1. 要解决什么问题

法规长文 + 大量表格与条款交叉引用时，常见失败包括：

1. **表格被切碎** —— 表头与数值行被拆开，阈值答错或丢行  
2. **图检索噪声大** —— 证据覆盖上去了，最终答案反而更糊  
3. **Agent 空转** —— 证据袋其实已经够用，模型仍反复检索同一子问题  
4. **评测不可信** —— 金标泄漏进在线路径，分数虚高  

本项目的应对路径：

**表原子切块（v3）→ 关系契约（v4）→ 取证 Agent + 充足性审核强制收网**

并如实汇报：图检索能帮助「找证据」，**不等于**自动得到更好答案。

---

## 2. 系统架构

![系统架构](docs/architecture.svg)

```text
法规 Markdown（prepared / 结构单元）
        │
        ▼
 LightRAG 抽取入库 ──► Neo4j（图，仅本地） + rag_storage v4（向量/KV，可随仓库）
        │
        ├──────────► WebUI /query（naive | hybrid | mix）
        │
        └──────────► harness 取证 Agent
                      规划 → 工具调用 → 充足性审核 → 作答 + 数值门控
```

| 层级 | 路径 | 职责 |
|------|------|------|
| 检索底座 | LightRAG 容器 | 建图、向量索引、HTTP 查询 |
| 定制注入 | `lightrag_custom/` | 抽取提示词、关系端点校验 |
| 在线 Agent | `harness/reg_harness/` | 工具循环、证据袋、审核收网、拒答 |
| 离线评测 | `benchmark/` | 金标、跑数、打分（默认 **不** 注入在线 Agent） |

更细的包结构见 [harness/ARCHITECTURE.md](harness/ARCHITECTURE.md)，  
控制层约定见 [harness/PROTOCOL.md](harness/PROTOCOL.md)。

---

## 3. 项目亮点（适合写进简历 / 面试）

1. **表感知切块（v3）**  
   23 张表各自独立入库 + 叙述单元，减轻表头/表体被硬切。表事实回归 **8/8**。

2. **关系契约（v4）**  
   42 类允许关系在「提示词 / schema_guard / 后处理」三处约束；类型非法关系 **106 → 0**。

3. **取证 Agent（不是一次检索拼 prompt）**  
   多步 `graph_search` / `vector_search`、证据袋组装、结构化作答，以及 **数值接地**（答案中的关键数字须在证据袋中出现）。

4. **充足性审核 + 强制收网**  
   每轮检索后由代码判断「够不够」；出现重复检索或证据袋停滞时 **强制 compose**，减少「假缺失」空转。  
   实测难题「6.11 五类误响应」：约 **10 步空转 → 4 步收网**，答案仍正确。

5. **评测与在线隔离**  
   默认不加载金标目录；benchmark 仅离线打分，避免金标污染在线 Agent。

**本项目不声称：**

- GraphRAG 全面优于纯向量检索  
- 已有 60 题正式冻结榜  
- 多标准、多知识库的生产级路由  

---

## 4. 仓库里有什么、没有什么

| 随 git 提供 | 仅本机、不入库 |
|-------------|----------------|
| 源码、`config/`、`compose`、无密钥的 profile | **含密钥的 `.env`** |
| `corpus/prepared`、`index_ready*` | **`data/neo4j`（约 500MB 图库）** |
| **最终版** `data/rag_storage/aeb_gb39901_v4_relation_guard/`（约 31MB，不含 LLM 缓存） | a0 / v2 / v3 索引、LLM 缓存 |
| v4 向量指纹 `state/embedding_fingerprint.aeb_gb39901_v4_relation_guard.json` | 其它 `state/*` 入库报告 |
| `benchmark/data` 金标 + 少量 `*report*.md` | `corpus/raw`、大批量跑分 jsonl |

**务必注意：**

- git 中的 v4 主要是 **向量与 KV**；**图数据在本机 Neo4j**，需执行 `make v4-up`，并按需重新入库。  
- 向量模型需与指纹一致（当前记录维度 **2560**，模型名见 fingerprint 文件）。  
- 指纹中的服务地址已脱敏，需在本地 `.env` 中自行配置。

---

## 5. 快速开始

环境要求：Docker、Python 3.10+、兼容 OpenAI 协议的 **对话模型 + 向量模型** API。

### 5.1 离线自检（可不启大模型）

```bash
git clone <本仓库地址>
cd <本仓库目录>

pip install -r requirements.txt
cd harness && pip install -e . && cd ..

cd harness
python3 -m unittest discover -s tests -v
python3 -m reg_harness.cli describe
```

### 5.2 启动服务（需要 API Key）

```bash
cp .env.example .env
# 编辑 .env：填写 NEO4J_PASSWORD、LLM_*、EMBEDDING_*
# 切勿把含真实密钥的 .env 提交到 git

make v4-up    # 启动 Neo4j + LightRAG，工作区为 v4
```

- Web 界面：http://127.0.0.1:9621  
- Neo4j：http://127.0.0.1:7474  

若图为空，按 Makefile 执行 v4 的 prepare / ingest / postprocess（见第 7 节）。  
请确认服务 `WORKSPACE` 为 `aeb_gb39901_v4_relation_guard`。

### 5.3 用 Agent 提问

简单题：

```bash
cd harness
python3 -m reg_harness.cli --profile-env .env.gb39901_v4 \
  ask "GB 39901—2025 适用于哪两类汽车？" --max-steps 6
```

难题（五类误响应 + 共同合格判据）：

```bash
python3 -m reg_harness.cli --profile-env .env.gb39901_v4 \
  ask "完整列出6.11规定的五类误响应场景，并说明所有场景共同的合格判据。" \
  --max-steps 10
```

### 5.4 截图（可选）

跑通后可将 WebUI / 终端截图放入 [`docs/screenshots/`](docs/screenshots/)，  
**不要**在截图中暴露 API Key 或内网地址。说明见该目录 README。

---

## 6. 目录说明

```text
.
├── harness/           # 取证 Agent（核心贡献）
├── lightrag_custom/   # 容器内定制：提示词 + schema_guard
├── scripts/           # 预处理、入库、探测
├── benchmark/         # 金标、打分脚本、短报告
├── config/            # 领域 / 国标关系 schema
├── corpus/            # prepared 语料 + index-ready 单元
├── data/rag_storage/  # 仅 v4 快照（不含 neo4j）
├── docs/              # 架构图、截图说明
├── compose.yaml       # Neo4j + LightRAG
└── Makefile           # v2 / v3 / v4 流水线入口
```

---

## 7. 实验线：A0 → v4

主交付与默认演示是 **v4**；A0–v3 为消融对照。完整命令见 Makefile 与 [PROJECT_STATUS.md](PROJECT_STATUS.md)。

| 标签 | 工作区名称 | 思路 |
|------|------------|------|
| A0 | `aeb_demo` | 原版 LightRAG 基线 |
| v2 | `aeb_gb39901_v2` | 叠加 schema / 中文抽取提示 |
| v3 | `aeb_gb39901_v3_table_chunks` | 46 个结构单元，表格原子化 |
| **v4** | `aeb_gb39901_v4_relation_guard` | 在 v3 上增加 42 类关系端点契约 |

### v3：表原子切块（摘要）

- 23 张 HTML 表各自独立入库，叙述拆为 23 单元，共 46 文档  
- 经 `/documents/texts` 提交，较大 chunk、零 overlap，失败可重试  

```bash
make v3-doctor && make v3-prepare && make v3-up && make v3-ingest
make v3-postprocess && make v3-test && make v3-fact-qa
```

### v4：关系守护（摘要）

- 提示词列出允许关系  
- `schema_guard` 在写入图与关系向量前校验  
- 后处理脚本再次校验合并后的图  

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

**稳定结论：**

1. 表切块能修好大量数值类问题。  
2. 关系合法 **不等于** 问答自动变强，仍需 Agent 与门控。  
3. 图模式常提高证据覆盖，噪声也可能抵消答案收益。

---

## 8. 语料说明

| 来源 | 在本项目中的角色 |
|------|------------------|
| **GB 39901-2025** | **唯一主动知识库** |
| UN R152、Euro NCAP 等 | 可在 `corpus/prepared` 中出现，**不作为** 主结论知识库 |

文本仅供学习研究，**不得**作为型式认证依据。请以正式出版物为准。详见 [NOTICE.md](NOTICE.md)。

---

## 9. 报告与评测

| 材料 | 路径 |
|------|------|
| Pilot 6 题报告 | [benchmark/results/pilot_6q_report.md](benchmark/results/pilot_6q_report.md) |
| 汇总报告 | [benchmark/results/benchmark_report.md](benchmark/results/benchmark_report.md) |
| 金标数据 | `benchmark/data/*.jsonl` |
| 评测脚本 | `benchmark/scripts/` |

大批量跑分结果默认不入库，需要时在本地重跑。

---

## 10. 安全约定

- 只提交 `.env.example` 与不含密钥的 `.env.gb39901*`  
- 禁止提交 API Key、Neo4j 数据卷、非 v4 大索引  
- 危险重置（会清空索引，必须显式确认）：

```bash
make reset-index CONFIRM=RESET_AEB_INDEX
```

---

## 11. 使用边界

本项目是 **GraphRAG 基线 + 取证 Agent 演示**，不是完整汽车领域本体库，也不是法规规则引擎。

- 回答可能出错  
- 涉及合规、认证时，必须以 **官方标准文本** 为准  

欢迎提 Issue / PR，流程见 [CONTRIBUTING.md](CONTRIBUTING.md)。
