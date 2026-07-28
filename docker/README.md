# Docker 说明

本仓库**不**把「整机环境 / 数据 / 密钥」打成胖镜像上传。运行时拆成：

| 组件 | 来源 |
|------|------|
| Neo4j | 官方镜像 `neo4j:5.26`（Compose 中固定 multi-arch digest） |
| LightRAG | 官方 `ghcr.io/hkuds/lightrag:v1.4.16`（固定 multi-arch digest） |
| 应用层钩子 | `lightrag_custom/`（挂载，或打入薄镜像） |
| 索引数据 | 卷挂载 `data/rag_storage`（v4 快照可进 git，无 LLM cache） |
| 密钥 | 仅 `.env`（不进镜像、不进 git） |

## 默认（推荐）：官方镜像 + 挂载

```bash
cp .env.example .env   # 填密钥与 NEO4J_PASSWORD
make v4-up             # pull neo4j + LightRAG，挂载 lightrag_custom
```

对应 `compose.yaml`：镜像使用便于阅读的版本 tag，并附加不可变 digest。

## 可选：薄应用层镜像

把 `lightrag_custom` bake 进镜像（仍**不含**密钥与索引数据）：

```bash
# 从 demo/aeb 目录
make lightrag-image
# 等价：
# docker build -f docker/lightrag/Dockerfile \
#   --build-arg BASE_IMAGE=ghcr.io/hkuds/lightrag:v1.4.16@sha256:67cc... \
#   -t evidencetrail-lightrag:v1.4.16-app .
```

使用该镜像启动：

```bash
make v4-up-app
# 或
docker compose --env-file .env --env-file .env.gb39901_v4 \
  -f compose.yaml -f compose.lightrag-app.yaml up -d neo4j lightrag
```

`compose.lightrag-app.yaml` 默认仍 bind-mount `./lightrag_custom` 便于改钩子热更新；若只要镜像内烘焙副本，注释掉该 volume 即可。
自定义 LightRAG 与 tools 镜像默认以 UID/GID 1000 的非 root 用户运行；若 Linux
主机目录属于其他 UID/GID，请在 `.env` 设置 `LIGHTRAG_UID`、`LIGHTRAG_GID`、
`TOOLS_UID`、`TOOLS_GID` 后重建镜像。

### 推送到 Docker Hub（可选，非必须）

仅推**薄层**、无数据：

```bash
docker tag evidencetrail-lightrag:v1.4.16-app YOUR_DOCKERHUB_USER/evidencetrail-lightrag:v1.4.16-app
docker push YOUR_DOCKERHUB_USER/evidencetrail-lightrag:v1.4.16-app
```

发布说明中写明：基于官方 LightRAG；无 API Key；无 Neo4j/rag 数据。

## tools 镜像

`tools/Dockerfile`：Python 脚本容器（prepare / ingest / 探测），`make` 里 `tools`
profile 使用。构建时只从带 SHA-256 的 `tools/requirements.lock` 安装依赖，与
LightRAG 主服务无关。

```bash
docker compose --profile tools build tools
```

## 安全

- 禁止把 `.env`、`data/neo4j`、含密钥的 cache 打进镜像或 push  
- 基础镜像固定到 `tag@digest`；升级时同时核验并更新 tag、digest，再做回归
- LightRAG 和 tools 使用只读根文件系统、最小 capabilities 与独立可写数据/临时挂载
