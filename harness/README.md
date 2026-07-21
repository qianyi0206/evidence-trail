# Regulation Evidence Harness（法规取证 Agent）

面向 **GB 39901-2025（轻型汽车 AEBS）** 单库场景的多步取证 Agent。  
底层用 LightRAG（图 + 向量）；本包负责 **计划循环、证据袋组装、作答与门控、轨迹**。

```text
问题
  → skill 决策（选工具 / 写子 query）
  → LightRAG mix|naive 检索
  → 图命中回源 chunk + 袋内原文优先
  → compose（分栏上下文）+ 数字/空袋门控
  → 结构化 JSON + trace
```

| 文档 | 内容 |
|------|------|
| **本 README** | 用法、流水线、配置、收尾结论 |
| [`PROTOCOL.md`](PROTOCOL.md) | 控制层规范（反贴题、金标隔离） |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | 包结构与扩展钩子 |
| [`../DELIVERY.md`](../DELIVERY.md) | 上级交付口径 |

**不修改 LightRAG 源码**；与 `../benchmark`、`../scripts` 并列。

---

## 1. 设计原则

1. **图求广、文答题**：图/三元组负责定位与导航；**事实（数字、表、枚举）以原文 chunk 为准**。
2. **Agent = 模型决策 + 代码护栏**：工具白名单、空袋拒答、数值 grounding、max_steps。
3. **控制层不写题剧本**：默认无 pilot 槽位/金标 catalog；金标仅离线评分。
4. **可观测**：`state.trace` 可 dump，便于对照 benchmark。
5. **与主流 GraphRAG 对齐的组装**：locate → `source_id` expand → 预算 → Text units 优先（见 §4）。

---

## 2. 快速开始

```bash
# 依赖
pip install httpx pyyaml

# LightRAG v4 工作区（示例）
cd /path/to/demo/aeb
make v4-up   # 或确保 :9621 已起，profile 为 .env.gb39901_v4

cd harness
python -m reg_harness.cli --profile-env .env.gb39901_v4 \
  ask "完整列出6.11规定的五类误响应场景，并说明所有场景共同的合格判据。"

# 写轨迹
python -m reg_harness.cli --profile-env .env.gb39901_v4 \
  ask "6.5至6.7车辆目标试验与其他试验的最低光照强度分别是多少？" \
  --max-steps 8 --dump-trace /tmp/t.json
```

环境：`demo/aeb/.env` + 可选 profile（如 `.env.gb39901_v4`）。  
CLI 的 `--profile-env` 写在 **子命令之前**。

### 其它命令

```bash
python -m reg_harness.cli --profile-env .env.gb39901_v4 describe
python -m reg_harness.cli --profile-env .env.gb39901_v4 retrieve "光照强度" --mode mix
python -m reg_harness.cli --profile-env .env.gb39901_v4 intent "是否强制三传感器"
```

Python：

```python
from reg_harness import build_stack

stack = build_stack(profile_env=".env.gb39901_v4")
state = stack.ask("GB 39901 适用于哪两类汽车？", max_steps=6)
print(state.final_answer)
```

---

## 3. 运行时流水线

默认工具：`graph_search`（默认 **mix**）、`vector_search`（naive）、`evidence_check`、`compose_answer`、`finalize`。  
精查 `clause_lookup` / `table_lookup` **默认关闭**。

```text
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ 决策 LLM    │────►│ graph / vector   │────►│ /query/data     │
│ skill+plan  │     │ + 子 query       │     │ enable_rerank   │
└─────────────┘     └────────┬─────────┘     └────────┬────────┘
                             │ entities/rels/chunks   │
                             ▼                        │
                    ┌──────────────────┐              │
                    │ source_id expand │◄─────────────┘
                    │ (backfill 全文)  │
                    └────────┬─────────┘
                             ▼
                    ┌──────────────────┐
                    │ compact 袋       │  chunk 配额 + 可选袋 rerank
                    │ text-primary     │
                    └────────┬─────────┘
                             ▼
                    ┌──────────────────┐
                    │ compose 分栏     │  Text units → Relations → Entities
                    │ + guards         │
                    └──────────────────┘
```

| 阶段 | 做什么 |
|------|--------|
| 检索侧 | LightRAG mix/naive；**token 分桶**（实体/关系默认各 15%，其余给 text units）；可选 qwen3-rerank |
| 回源 | 图命中的 `source_id` 拉全文；支持 `<SEP>` 多 id；已在袋中的 chunk 不重复占位 |
| 证据袋 | 条数上限（默认 20）；**chunk 至少约一半席**；entity/rel 各 ≤5 |
| 作答 | 分栏展示；数字/条款以 **Text units** 为准 |
| 门控 | 空袋拒答；答案中的关键数字须能在证据中对上（含 `1 000`→`1000` 写法） |

决策侧：停滞多轮无新增 → 提示 compose；达到 `max_steps` 且有证据则 force compose。

---

## 4. 证据组装（P0，相对主流 GraphRAG）

对齐思路：**图导航，文答题**；一关系多 chunk 时 expand 候选后 **配额/排序**，不全量倾倒。

| 机制 | 说明 |
|------|------|
| Token 分桶 | `/query/data` 的 `max_entity_tokens` / `max_relation_tokens` 为总预算的约 **15%+15%**，避免图摘要挤掉原文 |
| 忠实 expand | `source_id` 拆分 + 本地 `kv_store_text_chunks.json` 回源 |
| 袋配额 | `HARNESS_BAG_MAX_ENTITIES/RELATIONS`；顺序大致 chunk → relation → entity |
| 双 rerank | **检索侧**（容器内）+ **袋侧**（同 RERANK_*，失败回退启发式） |
| Compose 分栏 | Text units / Relations / Entities |
| 数字归一 | OCR 千分位空格与答案 `1000`/`2000` 对齐（交卷检查细节） |

**刻意不做：** 章节号剧本（如写死 8.1/第7章）当主路由；让模型每步拧 token 百分比。  
「证据不够」优先靠 **换 query/mode/再检索**，而不是改分桶旋钮。

---

## 5. 配置速查

| 变量 | 默认 | 含义 |
|------|------|------|
| `AEB_PROFILE_ENV` / `--profile-env` | — | 如 `.env.gb39901_v4` |
| `WORKSPACE` | profile | 与 LightRAG 一致；回填读 `data/rag_storage/<ws>/` |
| `HARNESS_GRAPH_DEFAULT_MODE` | `mix` | graph_search 默认 mode |
| `HARNESS_ENABLE_RERANK` | on | 检索侧 enable_rerank |
| `HARNESS_BAG_RERANK` | 有 RERANK_* 时 on | 袋侧 rerank |
| `HARNESS_CONTEXT_TOKENS` | 12000 | `/query/data` 总 token |
| `HARNESS_ENTITY_TOKEN_FRACTION` | 0.15 | 实体桶占比 |
| `HARNESS_RELATION_TOKEN_FRACTION` | 0.15 | 关系桶占比 |
| `HARNESS_BAG_LIMIT` | 20 | 证据袋条数 |
| `HARNESS_BAG_MAX_ENTITIES` | 5 | 袋内实体上限 |
| `HARNESS_BAG_MAX_RELATIONS` | 5 | 袋内关系上限 |
| `HARNESS_CHUNK_BACKFILL` | on | 图命中回源 |
| `HARNESS_CHUNK_BACKFILL_MAX` | 8 | 单次最多回源条数 |
| `HARNESS_MAX_STEPS` | 6 | 默认步数（CLI 可 `--max-steps`） |
| `HARNESS_PILOT_HEURISTICS` | off | 旧规则 intent/slots（对照） |
| `HARNESS_ENABLE_PRECISE_LOOKUP` | off | 注册 clause/table 精查 |
| `HARNESS_CATALOG_MODE` | `none` | 精查时 `gold` 才加载金标 catalog |

容器 rerank（v4）：`RERANK_BINDING=aliyun`，`RERANK_MODEL=qwen3-rerank`；key 回退 `LLM_BINDING_API_KEY`。  
改 `RERANK_*` 后需重启 lightrag 容器。

---

## 6. 目录结构

```text
harness/
  README.md                 # 本文件
  PROTOCOL.md / ARCHITECTURE.md
  reg_harness/
    runtime.py              # build_stack()
    loop.py                 # Agent 循环
    prompts.py              # 粗 skill
    config.py               # Settings
    compact.py / rerank.py  # 袋排序与袋侧 rerank
    bag_gaps.py             # 结构缺口提示（表引用/题干条款）
    guards.py               # 空袋/数字门控
    types.py                # AgentState、evidence_text 分栏
    tools/
      lightrag_retrieve.py  # vector/graph + expand + 分桶
      compose_answer.py
      evidence_check.py / finalize.py
      precise_lookup.py     # 可选
  tests/
  examples/sample_questions.yaml
```

---

## 7. 测试

```bash
cd harness
python3 -m unittest discover -s tests -q
```

重点用例：`test_p0_assembly`（分桶/expand/分栏/数字）、`test_chunk_backfill`、`test_bag_rerank`、`test_prompts_protocol`、`test_loop_behavior`。

Benchmark（GB 主集，离线 gold 仅评分）：

```bash
cd ..
python3 benchmark/scripts/run_harness_benchmark.py \
  --profile-env .env.gb39901_v4 --source gb --max-steps 8 \
  --output benchmark/results/run_harness_skill_gb50.jsonl \
  --score-output benchmark/results/answer_score_harness_skill_gb50.json
```

说明：官方 `primary_score` 对自由 JSON schema 很严，**内容向正确率**需另看关键事实；跨文档 10 题需多库 workspace，当前默认不跑。

---

## 8. 阶段结论（收尾）

### 做对了什么

- 垂域壳：**skill Agent + 门控 + 轨迹**，适合法规取证，而非单次 mix 黑箱。  
- 检索组装对齐主流：**定位 → 回源 → 原文优先 → 再作答**。  
- 默认去 pilot / 金标在线污染；协议见 PROTOCOL。  
- 典型难例（如 6.4 光照 1000/2000 lx）：在完整 chunk 进袋 + 组装修正后可答对。

### 仍知的边界

| 项 | 说明 |
|----|------|
| 肥 narrative 单元 | 如 5.3～6.4 混装，关键句在文末；中长期宜按条款切开 |
| 图抽取半截 | 三元组 description 可能不完整；故 **不能只靠图答题** |
| 袋侧 rerank 依赖百炼额度 | 失败时回退启发式 |
| 自动评分 schema | 字段名与 gold 不一致时 official primary 偏低 |
| 多 KB / Librarian | 架构预留，v0.1 不做 |

### 推荐默认使用

```bash
python -m reg_harness.cli --profile-env .env.gb39901_v4 ask "<问题>" --max-steps 6
```

工作区：`aeb_gb39901_v4_relation_guard`（以 profile `WORKSPACE` 为准）。

---

## 9. 与旧链路关系

| | 旧 | 本 harness |
|--|----|------------|
| 路径 | WebUI / benchmark 单次 mode 检索+生成 | 多步 tool loop |
| 检索 | 同 LightRAG `/query/data` | 同左 + 袋组装 |
| 评测 | `run_graphrag_benchmark.py` + `score_*` | `run_harness_benchmark.py` 适配同一套题 |

---

## 10. License / 范围

本目录为 car_project `demo/aeb` 实验与交付物的一部分；LightRAG 本体遵循其上游许可。  
**v0.1：单 KB GB39901 做深**；完整 50 题冻结、多标准联邦不在本 harness 交付必选项内。
