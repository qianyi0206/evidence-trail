# AEB GraphRAG 项目状态地图（v0.1 收紧）

> 交付口径见 [`DELIVERY.md`](DELIVERY.md)。本页负责导航：做了什么、结论是什么、什么不做。

---

## 1. 一句话

以 **GB 39901-2025 单库** 做深：LightRAG 建图消融（A0–v4）+ 法规取证 Agent 框架（`harness/`）+ pilot 诚实结论。  
**不**以多标准入库、英文协议启用、完整 50 题正式评测为本版交付。

---

## 2. 流水线

```text
GB OCR
  → prepare / v3 结构单元
  → LightRAG 建图（workspace A0|v2|v3|v4）
  → Neo4j + 向量
       → WebUI 经典问答
       → harness Agent（意图→工具→精查→compose→门控）
  → pilot / 表格回归结果（已有）
```

| 阶段 | 入口 |
|------|------|
| 语料 | `corpus/`（主用 GB；英文三份 disabled） |
| 建图 | `make v3-*` / `v4-*` / `gb-*` |
| Agent | `harness/` → `python -m reg_harness.cli …` |
| 结论 | `benchmark/results/pilot_6q_report.md` |

---

## 3. 建图方案（并列 workspace，都是 GB）

| 代号 | Workspace | 要点 |
|------|-----------|------|
| A0 | `aeb_demo` | 原版基线，证据可追溯性弱 |
| v2 | `aeb_gb39901_v2` | schema/prompt |
| v3 | `…_v3_table_chunks` | 46 单元；读表 8/8 |
| v4 | `…_v4_relation_guard` | 关系契约；非法边 0 |

---

## 4. 已跑过的验证

| 批次 | 结果锚点 |
|------|----------|
| Demo QA 8×2 | `results/qa_results_*.json` |
| 表格 Fact QA | `results/fact_qa_*.json`（v3/v4 8/8） |
| Pilot 6 题 | `benchmark/results/pilot_6q_report.md` |
| KG 结构分 | `benchmark/results/kg_score_*` |

**未做（本版不要求）：** formal 50 题主集、benchmark v1 冻结、多中文库入库。

---

## 5. 结论（可对外）

1. 表原子切分（v3）对数值事实有效。  
2. 关系守卫（v4）提升图合法性；**不自动等于** 最终 QA 第一。  
3. 图模式常抬高证据覆盖；**噪声** 可抵消回答收益 → 需要精查/门控/Agent，而不是只调 `mix`。  

---

## 6. Harness 框架状态

| 能力 | 状态 |
|------|------|
| 意图路由 + tools_prefer | ✅ 轻量规则，kb 默认 gb39901 |
| 多步取证 / 槽位 / compose 回环 | ✅ |
| clause/table 精查 + evidence id | ✅ |
| compact 压噪 | ✅ 基础 |
| 多 KB / Librarian 真建库 / merge | ⬜ 仅接口与文档 |
| eval 对接 pilot | ⬜ 本版不做 |

代码入口：`harness/reg_harness/`，架构：`harness/ARCHITECTURE.md`。

---

## 7. 本版「Done」定义

- [x] 单库 GB 故事与范围写清  
- [x] 英文三份标明不用于主结论  
- [x] 建图消融与 pilot 结论可引用  
- [x] Agent 框架可 `describe` / `intent` / `lookup` 演示  
- [x] 密钥路径 ignore（`.env` / `data/` 等）  
- [ ] （可选）live `ask` 截图/trace — 有 API 时再补  

---

## 8. 明确不在 v0.1

- 另找多篇中文标准并入库  
- 启用 UN R152 / Euro NCAP 作主库  
- 自动 schema 设计、自动图谱合并  
- 完整 50 题 formal 与冻结 v1  
