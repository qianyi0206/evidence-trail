# Apps

## Gradio 取证流水线演示

单页展示：

1. 提问（示例题）  
2. 可读答案 / 拒答  
3. 流水线轨迹（规划 → 检索 → 充分性 → 收网 → 作答）  
4. 证据袋摘要（chunk 优先）  
5. **v4 图谱静态截图**（你本地 Neo4j 导出）

不替代 LightRAG WebUI 或 Neo4j Browser。

### 准备截图

把 v4 总览图放到（文件名固定，便于自动加载）：

```text
docs/screenshots/neo4j-v4-overview.png   # 推荐：总览
docs/screenshots/neo4j-v4-focus.png      # 可选：6.11 / 局部
```

也可用 `neo4j-*.png` / `neo4j-*.jpg`。无图时页面会提示路径，不影响问答。

### 依赖与启动

```bash
cd demo/aeb          # 本仓库应用根目录
pip install -r requirements-ui.txt
cd harness && pip install -e . && cd ..

# 密钥与 Neo4j
cp -n .env.example .env   # 编辑 LLM / EMBEDDING / NEO4J_PASSWORD
make v4-up

python apps/gradio_pipeline.py
# http://127.0.0.1:7860
# python apps/gradio_pipeline.py --profile-env .env.gb39901_v4 --port 7860
```

### 说明

- 默认 skill：`HARNESS_CATALOG_MODE=none`，不加载金标  
- 需 LightRAG `http://127.0.0.1:9621` 健康  
- 轨迹与 CLI `--dump-trace` 同源（`state.trace`）

相关文档：

- [docs/architecture.svg](../docs/architecture.svg)  
- 根 [README.md](../README.md) §6  
