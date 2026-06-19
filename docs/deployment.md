# 部署指南

> 返回 [文档首页](README.md) · 故障排查见 [deploy-troubleshooting.md](deploy-troubleshooting.md)

生产站点示例：**[https://cnpoetry.top/](https://cnpoetry.top/)**

通过 SSH + rsync 将项目同步到 ECS，在远端 `docker compose build` 启动；Nginx 监听 80 端口反代到容器 `8000`。

**推荐 ECS 规格**：2 vCPU / 4 GiB 内存起，系统盘 ≥ 40 GB（需加载 PyTorch 与 BGE 模型）。安全组入站放行 **22**（SSH）、**80**（HTTP）、**443**（HTTPS，若启用 SSL）。

## 一次性初始化 ECS

```bash
cp scripts/deploy/deploy.env.example scripts/deploy/deploy.env
# 编辑 deploy.env：ECS_HOST、SSH_KEY、REMOTE_DIR 等
./scripts/deploy/setup-ecs.sh
```

`setup-ecs.sh` 会在 ECS 上安装 Docker、Nginx，并写入反向代理配置（含 SSE 流式支持）。

## 配置环境变量（dev / prod 隔离）

| 环境 | 配置文件 | 用途 |
|------|----------|------|
| 本地开发 | `.env` | `cp .env.example .env`，本地跑 uvicorn / docker compose |
| ECS 生产 | `.env.prod` | `cp .env.prod.example .env.prod`，仅由 `deploy.sh` 上传 |

两套配置互不影响：发布脚本**只上传 `.env.prod`**，不会覆盖本地 `.env`。

**本地 dev**（`.env.example` → `.env`）：

```bash
cp .env.example .env
# 编辑 .env，填入 DashScope API Key 等
```

**ECS prod**（`.env.prod.example` → `.env.prod`）：

```bash
cp .env.prod.example .env.prod
# 编辑 .env.prod：生产 API Key、独立 JWT_SECRET_KEY、CORS 域名等
```

生产环境建议：

```env
APP_ENV=production
EMBEDDING_MODEL=./data/models/BAAI--bge-small-zh-v1.5
RERANK_MODEL=./data/models/BAAI--bge-reranker-base
HF_ENDPOINT=https://hf-mirror.com
LANGSMITH_PROJECT=poetry-agent-prod
JWT_SECRET_KEY=<与 dev 不同的随机长字符串>
CORS_ORIGINS=https://cnpoetry.top,http://<ECS公网IP>
```

## 首次发布

应用依赖 Embedding/Rerank 模型与向量库，首次部署二选一：

- **推荐（本地已构建好）**：本地执行 `python scripts/download_models.py` 与 `python scripts/build_index.py`，再同步数据发布：

```bash
./scripts/deploy/deploy.sh --with-data
```

- **在 ECS 构建**：先 `./scripts/deploy/deploy.sh`，SSH 登录后进入容器下载模型并建索引（耗时较长，需 ECS 内存 ≥ 4GB）。

## 日常更新

```bash
./scripts/deploy/deploy.sh              # 同步配置并启动（ACR 模式只 pull，不 build）
./scripts/deploy/deploy.sh --with-data  # 同步 data/（语料、模型、向量库）
./scripts/deploy/deploy.sh --env-only   # 仅更新 .env.prod 并重启
./scripts/deploy/deploy.sh --pull       # 仅拉取最新 ACR 镜像并重启
```

## 推荐：阿里云 ACR 部署（避免 ECS 运行时 build）

在 ECS 上构建镜像耗时长（torch 等依赖）。推荐 **云端 build → push ACR → ECS pull 启动**。

> **说明**：ACR **个人版**是镜像仓库，没有「在 ACR 控制台里自动 build Dockerfile」。
> 常见做法：在 **ECS 上 build**（本脚本）或 **本地 build**（`build-push-acr.sh`），再 push 到 ACR。

**1. 配置 `scripts/deploy/deploy.env`**

```env
POETRY_AGENT_IMAGE=crpi-xxxxx.ap-southeast-1.personal.cr.aliyuncs.com/bobpoc/poetryagent:latest
ACR_REGISTRY=crpi-xxxxx.ap-southeast-1.personal.cr.aliyuncs.com
ACR_USERNAME=你的阿里云账号
ACR_PASSWORD=ACR控制台-访问凭证-固定密码
```

**2. 在 ECS 上构建并 push ACR（推荐，不在本地打镜像）**

```bash
./scripts/deploy/build-on-ecs.sh
# 强制不用缓存（改了 Dockerfile 后）：
./scripts/deploy/build-on-ecs.sh --no-cache
```

**或本地 Mac 构建 push：**

```bash
./scripts/deploy/build-push-acr.sh --no-cache
```

**3. ECS 首次登录 ACR（未配置 ACR_USERNAME/PASSWORD 时手动一次）**

```bash
ssh root@<ECS_IP>
docker login crpi-xxxxx.ap-southeast-1.personal.cr.aliyuncs.com
```

**4. 部署到 ECS（只 pull，不 build）**

```bash
./scripts/deploy/deploy.sh --with-data   # 首次（同步 data/models、chroma_db）
./scripts/deploy/deploy.sh --pull        # 日常：拉新镜像并重启
```

ECS 上不再执行 `docker build`，启动约 **1～2 分钟**。

**注意**：模型与向量库仍在 ECS 的 `./data/` 卷中，`.env.prod` 请用容器路径：

```env
EMBEDDING_MODEL=./data/models/BAAI--bge-small-zh-v1.5
RERANK_MODEL=./data/models/BAAI--bge-reranker-base
```

## 日常更新（ECS 本地 build 方式）

```bash
./scripts/deploy/deploy.sh              # 同步代码并在 ECS build（较慢）
./scripts/deploy/deploy.sh --env-only   # 仅更新 .env.prod 并重启
```

部署成功后访问 `https://cnpoetry.top/` 或 `http://<ECS公网IP>/`。

## 远端运维

SSH 登录 ECS 后，在项目目录执行：

```bash
cd /opt/poetry-agent   # 或 deploy.env 中的 REMOTE_DIR
./scripts/deploy/remote-compose.sh logs
./scripts/deploy/remote-compose.sh health
./scripts/deploy/remote-compose.sh restart
```

## 故障排查

| 现象 | 处理 |
|------|------|
| 502 Bad Gateway | 容器未启动 → `remote-compose.sh logs` |
| RAG 无检索结果 | `data/chroma_db` 未同步或未建索引 → `deploy.sh --with-data` 或容器内执行 `build_index.py` |
| 模型下载失败 | 确认 `.env.prod` 中 `HF_ENDPOINT=https://hf-mirror.com`；ECS 安全组出站放行 HTTPS |

更多见 [deploy-troubleshooting.md](deploy-troubleshooting.md)。

## 部署架构

详见 [architecture.md · 部署架构](architecture.md#7-部署架构)。
