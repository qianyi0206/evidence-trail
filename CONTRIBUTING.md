# 参与贡献 · EvidenceTrail

感谢关注 **EvidenceTrail**（基于 GraphRAG 的文档取证 Agent）。  
本仓库是 [LightRAG](https://github.com/HKUDS/LightRAG) 之上的 **应用层**；样例域为 GB 39901 AEBS，方法可迁移到其它技术文档。

## 基本约定

1. **禁止提交密钥** — 不要提交含真实 API Key 的 `.env`。使用 `.env.example` 与无密钥 profile（`.env.gb39901*`）。
2. **禁止提交 Neo4j 数据卷**（`data/neo4j/`）及非 v4 工作区。仓内仅保留最终版  
   `data/rag_storage/aeb_gb39901_v4_relation_guard/`（不含 LLM cache）。
3. **PR 尽量小** — Agent 行为、打分、文档、入库脚本尽量分开提。
4. **金标仅离线** — 在线路径默认不加载 benchmark 金标；除非显式 `HARNESS_CATALOG_MODE=gold`。

## 开发环境

```bash
# Python 3.10+
pip install -r requirements.txt
cd harness && pip install -e . && cd ..

# 单元测试（多数不需要 LLM / Docker）
cd harness && python3 -m unittest discover -s tests -v
cd ../benchmark && PYTHONPATH=scripts python3 -m unittest tests.test_benchmark -v
```

联调：Docker Desktop，`cp .env.example .env`，然后 `make v4-up`（见根 README）。

## 代码风格

- Python：4 空格缩进，尽量类型标注；长生命周期代码用现有日志习惯。
- Agent 控制逻辑在 `harness/reg_harness/`；LightRAG 侧补丁在 `lightrag_custom/`。
- 代码注释英文；面向用户的 Agent 提示词可为中文（领域需要）。

## 提交 PR 前

- [ ] `cd harness && python3 -m unittest discover -s tests`
- [ ] 无新密钥、无大二进制
- [ ] 行为或隔离规则变更时更新 README / PROTOCOL
- [ ] 说明改了什么、为什么

## 反馈问题

请说明：系统、Python 版本、是否已起 Docker/LightRAG、profile（如 `.env.gb39901_v4`）、最小复现命令。打码 API Key。

## 许可

贡献默认按本仓库 [MIT License](LICENSE) 接受。LightRAG 遵循其自身许可证，见 [NOTICE.md](NOTICE.md)。
