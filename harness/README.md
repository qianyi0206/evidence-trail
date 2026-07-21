# EvidenceTrail · Agent 实现（`reg_harness`）

本目录是 **EvidenceTrail** 项目的在线 Agent 包：多步取证编排。  
样例配置面向 **GB 39901-2025（轻型汽车 AEBS）** 单库；逻辑不绑定该标准。

底层用 LightRAG（图 + 向量）；**本包负责** 计划循环、证据袋组装、充足性审核、作答与门控、轨迹 trace。

```text
问题
  → skill 决策（选工具 / 写子 query）
  → LightRAG mix|naive 检索
  → 图命中回源 chunk + 袋内原文优先
  → 充足性审核（够则收网，防空转）
  → compose（分栏上下文）+ 数字/空袋门控
  → 结构化 JSON + trace（证据轨迹）
```

| 文档 | 内容 |
|------|------|
| **本 README** | 用法、流水线、配置 |
| [`PROTOCOL.md`](PROTOCOL.md) | 控制层规范（反贴题、金标隔离） |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | 包结构与扩展钩子 |
| [项目总 README](../README.md) | EvidenceTrail 定位、快速开始、样例域说明 |

**不修改 LightRAG 源码**；与 `../benchmark`、`../scripts` 并列。

---

## 1. 设计原则

1. **图求广、文答题**：图/三元组负责定位与导航；**事实（数字、表、枚举）以原文 chunk 为准**。
2. **Agent = 模型决策 + 代码护栏**：工具白名单、空袋拒答、数值 grounding、充足性强制收网、max_steps。
3. **控制层不写题剧本**：默认无 pilot 槽位/金标 catalog；金标仅离线评分。
4. **可观测**：`state.trace` 可 dump，便于对照 benchmark。
5. **与主流 GraphRAG / Agentic RAG 对齐的组装**：locate → `source_id` expand → 预算 → Text units 优先（见 §4）。

---

## 2. 快速开始

```bash
# 依赖（也可在仓库根目录 pip install -r requirements.txt）
pip install httpx pyyaml
# 或
pip install -e .

# 仓库根目录已起 LightRAG v4 时：
python3 -m reg_harness.cli --profile-env .env.gb39901_v4 \
  ask "GB 39901—2025 适用于哪两类汽车？"

# 写轨迹
python3 -m reg_harness.cli --profile-env .env.gb39901_v4 \
  ask "6.5至6.7车辆目标试验与其他试验的最低光照强度分别是多少？" \
  --max-steps 8 --dump-trace /tmp/t.json
```

环境：仓库根目录 `.env` + 可选 profile（如 `.env.gb39901_v4`）。  
CLI 的 `--profile-env` 写在 **子命令之前**。

### 其它命令

```bash
python3 -m reg_harness.cli --profile-env .env.gb39901_v4 describe
python3 -m reg_harness.cli --profile-env .env.gb39901_v4 retrieve "光照强度" --mode mix
python3 -m reg_harness.cli --profile-env .env.gb39901_v4 intent "是否强制三传感器"
```

Python：

```python
from reg_harness import build_stack

stack = build_stack(profile_env=".env.gb39901_v4")
state = stack.ask("GB 39901 适用于哪两类汽车？", max_steps=6)
print(state.final_answer)
```

单元测试：

```bash
python3 -m unittest discover -s tests -v
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
                    │ sufficiency 审核 │  够 → 强制 compose；空转 → 收网
                    └────────┬─────────┘
                             ▼
                    ┌──────────────────┐
                    │ compose + guards │  数值接地 / 空袋拒答
                    └──────────────────┘
```

其余章节（配置项、工具表、协议对齐）见历史文档与 `PROTOCOL.md`；项目级说明以仓库根 [README.md](../README.md) 为准。
