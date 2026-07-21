# EvidenceTrail

**基于 GraphRAG 的文档取证 Agent（Agentic RAG）**

面向智能汽车等场景：**长技术文档 + 表格/条款交叉 + 答案必须可核对**。  
底层使用开源 [LightRAG](https://github.com/HKUDS/LightRAG)（图 + 向量）；本仓库实现 **多步取证编排、入库策略、质量门控与离线评测**。

| | |
|--|--|
| **GitHub 仓库名建议** | `evidence-trail` |
| **Python 包（实现）** | `harness/reg_harness`（CLI：`python -m reg_harness`） |
| **样例域** | GB 39901-2025 轻型汽车 **AEBS** 法规（验证方法，可替换为其它技术文档） |

同一套思路可迁移到试验规范、标定说明、故障诊断、内部设计文档等需要「有依据、能拒答」的知识问答。

| 本仓库（应用层） | 外部依赖（不收录其源码） |
|------------------|--------------------------|
| 取证 Agent `harness/` | LightRAG Docker **v1.4.16** |
| 入库与关系约束 `lightrag_custom/`、`scripts/` | Neo4j + 对话 / 向量 API |
| 离线评测 `benchmark/` | 样例语料见 `corpus/`（prepared） |

> **一句话：** EvidenceTrail = **跑在 GraphRAG 上的证据轨迹 Agent**（plan → retrieve → audit → grounded answer），不是 LightRAG 复现；国标 AEBS 是高相关压力测试样例。

架构图：[docs/architecture.md](docs/architecture.md) · 贡献：[CONTRIBUTING.md](CONTRIBUTING.md) · 声明：[NOTICE.md](NOTICE.md) · 许可证：[MIT](LICENSE)

---

## 1. 背景与动机

智能汽车研发里，大量知识写在 **长文档** 里：法规、试验规程、标定与诊断说明等。它们和通用网页问答不同：

| 痛点 | 表现 |
|------|------|
| 结构硬 | 表格、条款号、例外条件交织 |
| 答案要可核对 | 阈值/枚举必须能指回原文，不能「像模像样地编」 |
| 单次 RAG 不够 | 往往要多跳检索、补表、再综合 |
| 评测易虚高 | 金标一旦泄漏进在线路径，分数不可信 |

**EvidenceTrail** 用样例域 **GB 39901（AEBS）** 把上述问题打穿：主动安全法规与智驾安全强相关、文档难、对引用要求高。  
**方法本身不绑定这一本标准**——换语料与 schema 即可迁到其它技术文档集。

---

## 2. 系统架构

![系统架构](docs/architecture.svg)

```text
技术文档 Markdown（本仓样例：GB 39901 prepared / 结构单元）
        │
        ▼
 LightRAG 抽取入库 ──► Neo4j（图，本地） + 向量/KV（v4 快照可随仓）
        │
        ├──────────► WebUI 标准检索（naive / hybrid / mix）
        │
        └──────────► EvidenceTrail Agent（本仓核心）
              问题
                → 决策：选工具 / 写子 query
                → LightRAG 检索（图+向量，mix|naive）
                → 图命中回源 chunk，袋内原文优先
                → 充足性审核（代码）：够则收网，防空转
                → compose + 数字/空袋门控
                → 结构化 JSON + 证据轨迹 trace
```

| 层级 | 路径 | 职责 |
|------|------|------|
| 检索底座 | LightRAG 容器 | 建图、向量、HTTP 查询 |
| 定制注入 | `lightrag_custom/` | 领域提示词、关系端点校验 |
| **EvidenceTrail** | `harness/reg_harness/` | 计划循环、证据袋、审核收网、门控作答 |
| 离线评测 | `benchmark/` | 金标与打分（默认 **不** 注入在线路径） |

包结构细节：[harness/ARCHITECTURE.md](harness/ARCHITECTURE.md) · 控制约定：[harness/PROTOCOL.md](harness/PROTOCOL.md) · harness 说明：[harness/README.md](harness/README.md)

---

## 3. 方法要点（可写进简历）

1. **文档侧：让检索「吃得进表」**  
   表原子切块（v3）：表格独立成文档，避免表头/数值行被 token 切断。样例域表事实回归 **8/8**。

2. **图谱侧：约束关系合法性**  
   关系契约（v4）：允许的关系类型与端点在提示词 / 运行时 guard / 后处理三处约束。样例域类型非法关系 **106 → 0**。

3. **在线侧：多步取证 Agent，而不是一次 retrieve 拼 prompt**  
   工具规划 → 检索 → 证据袋（图命中回源、原文优先）→ 结构化作答；**数值接地**（关键数字须在袋中出现）与空袋拒答。

4. **控制侧：充足性审核 + 强制收网**  
   检索后由代码判断「是否已够作答」；重复检索 / 袋停滞时强制 compose，减轻「假缺失」空转。  
   样例难题（6.11 五类误响应）：约 **10 步空转 → 4 步收网**，结论仍正确。

5. **评测侧：金标与在线隔离**  
   默认不加载评测金标进 Agent；benchmark 仅离线使用，避免分数被「开卷」污染。

**不声称：** 全面碾压纯向量 RAG；已有大规模生产多库路由；可直接用于型式认证。

---

## 4. 仓库内容边界

| 随 git 提供 | 仅本机 |
|-------------|--------|
| 源码、配置、compose、无密钥 profile | **含密钥的 `.env`** |
| 样例语料 `corpus/prepared`、`index_ready*` | **`data/neo4j`（约 500MB）** |
| 最终工作区向量/KV：`…/aeb_gb39901_v4_relation_guard/`（约 31MB） | a0/v2/v3 索引、LLM 缓存 |
| v4 embedding 指纹（host 已脱敏） | 其它 state 报告 |
| 评测金标 + 少量报告 md | 大批量跑分 jsonl、`corpus/raw` |

**注意：** 仓内 v4 快照主要是 **向量与 KV**；**图在 Neo4j**，需本地 `make v4-up` 并按需入库。  
向量模型维度须与指纹一致（当前记录 **2560**）。

---

## 5. 快速开始

需要：Docker、Python 3.10+、兼容 OpenAI 协议的对话与向量 API。

### 5.1 离线自检

```bash
git clone <本仓库>
cd <本仓库>

pip install -r requirements.txt
cd harness && pip install -e . && cd ..

cd harness
python3 -m unittest discover -s tests -v
python3 -m reg_harness.cli describe
```

### 5.2 启动检索服务

```bash
cp .env.example .env
# 填写 NEO4J_PASSWORD、LLM_*、EMBEDDING_* —— 勿提交 .env

make v4-up
```

- WebUI：http://127.0.0.1:9621  
- Neo4j：http://127.0.0.1:7474  

图为空时按 Makefile 做 v4 的 prepare / ingest（见第 7 节）。  
工作区名：`aeb_gb39901_v4_relation_guard`。

### 5.3 运行取证 Agent（样例问题）

```bash
cd harness

# 简单事实
python3 -m reg_harness.cli --profile-env .env.gb39901_v4 \
  ask "GB 39901—2025 适用于哪两类汽车？" --max-steps 6

# 多条款综合（更难）
python3 -m reg_harness.cli --profile-env .env.gb39901_v4 \
  ask "完整列出6.11规定的五类误响应场景，并说明所有场景共同的合格判据。" \
  --max-steps 10
```

跑通后可按 [docs/screenshots/](docs/screenshots/) 补充截图（勿暴露密钥）。

---

## 6. 目录结构

```text
.
├── harness/           # EvidenceTrail Agent 实现（包名 reg_harness）
├── lightrag_custom/   # LightRAG 侧定制（提示词 / schema_guard）
├── scripts/           # 预处理与入库
├── benchmark/         # 样例域金标与打分
├── config/            # schema 配置
├── corpus/            # 样例语料（prepared）
├── data/rag_storage/  # 仅 v4 向量/KV 快照
├── docs/              # 架构图等
├── compose.yaml
└── Makefile
```

---

## 7. 样例域实验线（A0 → v4）

以下为 **GB 39901 样例** 上的消融，用来证明入库与约束策略；主演示默认 **v4**。

| 标签 | 工作区 | 思路 |
|------|--------|------|
| A0 | `aeb_demo` | 原版 LightRAG |
| v2 | `aeb_gb39901_v2` | 领域提示 / schema 叠加 |
| v3 | `aeb_gb39901_v3_table_chunks` | 表原子 + 结构单元 |
| **v4** | `aeb_gb39901_v4_relation_guard` | + 关系端点契约 |

```bash
# v3
make v3-doctor && make v3-prepare && make v3-up && make v3-ingest
make v3-postprocess && make v3-test && make v3-fact-qa

# v4（推荐）
make v4-doctor && make v4-prepare && make v4-up && make v4-ingest
make v4-postprocess && make v4-test && make v4-fact-qa
```

样例域对比（2026-07-18）：

| 指标 | v3 | **v4** |
|------|---:|-------:|
| 结构文档数 | 46 | 46 |
| 类型非法关系 | 106 | **0** |
| 表事实 + 引用 | 8/8 | **8/8** |

更多状态：[PROJECT_STATUS.md](PROJECT_STATUS.md)

---

## 8. 样例语料说明

| 来源 | 角色 |
|------|------|
| **GB 39901-2025** | 本仓库 **主动** 演示与评测用的样例库 |
| UN R152 / Euro NCAP 等 | 可存在于 prepared，不作为主结论库 |

仅供学习研究，**不能**替代正式标准文本，也 **不能** 用于型式认证。见 [NOTICE.md](NOTICE.md)。

---

## 9. 评测与报告

| 材料 | 路径 |
|------|------|
| Pilot 报告 | [benchmark/results/pilot_6q_report.md](benchmark/results/pilot_6q_report.md) |
| 汇总报告 | [benchmark/results/benchmark_report.md](benchmark/results/benchmark_report.md) |
| 金标 | `benchmark/data/*.jsonl` |
| 脚本 | `benchmark/scripts/` |

---

## 10. 安全

- 勿提交真实 `.env`  
- 勿提交 Neo4j 数据卷与非 v4 大索引  
- 清空索引（危险，需显式确认）：

```bash
make reset-index CONFIRM=RESET_AEB_INDEX
```

---

## 11. 边界与后续

- 这是 **方法验证 + 工程 demo**，不是车企生产知识中台，也不是法规规则引擎。  
- 回答可能错误；合规场景请以官方/内部受控文本为准。  
- 若迁移到其它文档集：替换语料与 schema 配置，复用 EvidenceTrail 的 Agent 循环、门控与评测隔离即可。

欢迎 Issue / PR：[CONTRIBUTING.md](CONTRIBUTING.md)

---

## 12. 命名与引用

| 用途 | 名称 |
|------|------|
| 项目品牌 | **EvidenceTrail** |
| 仓库名（建议） | `evidence-trail` |
| 形态关键词 | Agentic RAG · grounded / evidence-based answering |
| 代码入口 | `python -m reg_harness.cli …` |

简历可写：**EvidenceTrail：基于 GraphRAG 的汽车技术文档取证 Agent（样例域 GB 39901 AEBS）**。
