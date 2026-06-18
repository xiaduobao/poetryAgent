# 部署问题汇总

本文档收集 poetryAgent 项目在阿里云 ECS + ACR 部署过程中遇到的实际问题、原因与解决方案。

---

## 1. 本地 dev 与 ECS 生产环境配置互相覆盖

### 现象
- 本地改 `.env` 后执行 `./scripts/deploy/deploy.sh`，ECS 上的生产配置被覆盖
- 或本地开发配置（`APP_ENV=development`、本地模型路径、localhost CORS）跑到生产环境

### 原因
- 早期 `deploy.sh` 把本地 `.env` scp 到 ECS
- `docker-compose.yml` 曾硬编码 `APP_ENV=production`，与 `.env` 内容冲突
- dev / prod 共用一份配置文件

### 解决方案（已实施）
| 环境 | 配置文件 | APP_ENV |
|------|----------|---------|
| 本地开发 | `.env` | `development` |
| ECS 生产 | `.env.prod` | `production` |

- `deploy.sh` **只上传 `.env.prod`**，不再碰本地 `.env`
- `docker-compose.dev.yml` 使用 `env_file: .env`；`docker-compose.prod.yml` 使用 `env_file: .env.prod`
- 生产建议独立配置：`JWT_SECRET_KEY`、`CORS_ORIGINS`（ECS IP/域名）、`LANGSMITH_PROJECT=poetry-agent-prod`

### 常用命令
```bash
cp .env.example .env              # 本地 dev
cp .env.prod.example .env.prod    # ECS prod

./scripts/deploy/deploy.sh --env-only   # 只更新生产环境变量
```

---

## 2. Docker Hub 429 Too Many Requests（构建基础镜像失败）

### 现象
```
failed to solve: node:20-slim: failed to copy: ...
429 Too Many Requests - toomanyrequests: You have reached your unauthenticated pull rate limit
```
ACR 云构建日志类似：
```
Build artifact crpi-.../bobpoc/poetryagent:latest fail: "exit status 1"
```

### 原因
- Dockerfile 中 `FROM node:20-slim` / `FROM python:3.11-slim` 默认从 **docker.io** 拉取
- Docker Hub 对未登录 IP 限流：**约 10 次/小时**
- 在 ECS、本地 Mac、**ACR 控制台云构建** 中都会触发（不限于某一环境）

### 解决方案（按推荐顺序）

#### 方案 A：阿里云同区域官方代理（推荐）
```dockerfile
FROM registry.ap-southeast-1.aliyuncs.com/library/node:20-slim
FROM registry.ap-southeast-1.aliyuncs.com/library/python:3.11-slim
```
- `library/` 对应 Docker Hub 官方镜像
- 与新加坡 ACR 同区域，构建拉取更稳定

#### 方案 B：同步到个人 ACR（最稳）
1. ACR 控制台 → **制品中心** → 订阅 `node:20-slim`、`python:3.11-slim`
2. 同步到 `bobpoc` 命名空间
3. Dockerfile 改为：
```dockerfile
FROM crpi-60eut63p9vp6h7li.ap-southeast-1.personal.cr.aliyuncs.com/bobpoc/node:20-slim
FROM crpi-60eut63p9vp6h7li.ap-southeast-1.personal.cr.aliyuncs.com/bobpoc/python:3.11-slim
```

#### 方案 C：第三方镜像代理（临时备用）
```dockerfile
FROM docker.m.daocloud.io/library/node:20-slim
# 或 docker.1ms.run/library/node:20-slim
```
当前 Dockerfile 支持 build-arg：
```dockerfile
ARG NODE_IMAGE=docker.m.daocloud.io/library/node:20-slim
ARG PYTHON_IMAGE=docker.m.daocloud.io/library/python:3.11-slim
```

#### 方案 D：Docker Hub 登录（治标）
```bash
docker login
```
免费账号约 100 次/小时，CI/云构建共享 IP 仍可能不够。

---

## 3. 镜像构建位置混乱（ECS / 本地 / ACR）

### 现象
- 在 ECS 上 `docker build` 耗时长（PyTorch 等依赖）、内存占用高
- 本地 Mac build 慢且也可能遇到 Docker Hub 429
- 不确定该在哪构建、ECS 该 pull 还是 build

### 最终方案（推荐工作流）
```
ACR 控制台手动构建 → push 到个人仓库 → ECS 只 pull 启动
```

| 步骤 | 操作 |
|------|------|
| 构建 | ACR 控制台「镜像构建」（绑定代码源 + Dockerfile） |
| 镜像地址 | `crpi-60eut63p9vp6h7li.ap-southeast-1.personal.cr.aliyuncs.com/bobpoc/poetryagent:latest` |
| 部署 | `./scripts/deploy/deploy.sh` 或 `--pull` |
| ECS | **不执行** `docker build` |

### 备选脚本（非主路径）
- `build-on-ecs.sh` — ECS 上 build + push ACR
- `build-push-acr.sh` — 本地 Mac build + push ACR

---

## 4. 两个 ACR 地址容易混淆

### 现象
不清楚 `registry.ap-southeast-1.aliyuncs.com` 和 `crpi-...personal.cr.aliyuncs.com` 的区别。

### 说明
| 地址 | 用途 |
|------|------|
| `registry.ap-southeast-1.aliyuncs.com/library/...` | 阿里云**官方镜像代理**，Dockerfile `FROM` 拉 node/python 等基础镜像 |
| `crpi-60eut63p9vp6h7li.ap-southeast-1.personal.cr.aliyuncs.com/bobpoc/poetryagent:latest` | **个人 ACR 仓库**，存放构建好的应用镜像，ECS 部署时 pull |

---

## 5. ECS 首次 pull 私有镜像失败

### 现象
```
Error response from daemon: pull access denied / unauthorized
```

### 原因
个人 ACR 镜像需要登录才能 pull。

### 解决方案
```bash
# SSH 到 ECS，只需一次
docker login crpi-60eut63p9vp6h7li.ap-southeast-1.personal.cr.aliyuncs.com
# 用户名：阿里云账号
# 密码：ACR 控制台 → 访问凭证 → 固定密码
```
或在 `deploy.env` 配置 `ACR_USERNAME` / `ACR_PASSWORD`，`deploy.sh` 会自动远程登录。

---

## 6. 生产环境路径与配置常见错误

### 现象
- ECS 上 RAG 无结果、模型加载失败
- 容器内找不到 embedding 模型

### 原因
`.env.prod` 使用了本地 Mac 绝对路径，例如：
```env
EMBEDDING_MODEL=/Users/wangjiabao/git/poetryAgent/models/...
```

### 正确配置（容器内路径）
```env
EMBEDDING_MODEL=./data/models/BAAI--bge-small-zh-v1.5
CHROMA_PERSIST_DIR=/app/data/chroma_db
CORPUS_DIR=/app/data/corpus
```
首次部署需同步 data：
```bash
./scripts/deploy/deploy.sh --with-data
```

---

## 7. apt-get / pip 构建卡住 [build]

### 现象
- Docker build 在 `apt-get update` 阶段卡住 10～30 分钟
- `pip install torch` 下载 `nvidia-cublas` 400MB+ 或 torch 532MB 极慢

### 原因
- ECS 访问 Debian 官方源慢 → 换阿里云 Debian 源
- `pip install torch` 默认拉 **CUDA/GPU 版**（2GB+），ECS 无 GPU 完全用不上
- 第二步 `pip install -r requirements.txt` 可能再次从 PyPI 拉回 GPU 版 torch

### 解决方案
- Dockerfile：`sed` 替换为 `mirrors.aliyun.com` Debian 源
- 先装 CPU 版 torch：`--index-url https://download.pytorch.org/whl/cpu`
- 用 `constraints.txt` 锁定 `torch==x.x.x+cpu`，再装其余依赖
- 构建后校验：`pip list | grep -i nvidia` 应为空

### 状态
- [x] 已解决（2026-06-16）

---

## 8. 镜像体积 ~3GB 含 nvidia 包 [build]

### 现象
```bash
docker run --rm <image> pip list | grep -i nvidia
# 出现 nvidia-cublas、cudnn 等十几个包
```

### 原因
构建时 constraints 未生效或 pip 顺序错误，混入了 CUDA 依赖。

### 解决方案
- 多阶段 Dockerfile + 装完依赖后 nvidia 包检测失败则 exit 1
- `.dockerignore` 排除 `data/`、`.env`、`.env.prod` 等

### 状态
- [x] 已解决（2026-06-16）

---

## 9. 启动时 Alembic 日志后假死 [runtime]

### 现象
```
INFO  [app.main] LangSmith tracing enabled ...
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
```
之后 1～2 分钟无日志，像卡住。

### 原因
- Dockerfile CMD 与 `lifespan` → `init_db()` **重复跑** Alembic
- PostgreSQL 路径曾在线程内 `asyncio.run(asyncpg)`，与 uvicorn 事件循环冲突
- 服务实际约 2 分钟后可变为 healthy（假死非 PG 锁死锁）

### 解决方案
- `init_db` 查 `alembic_version`，已在 head 则跳过
- 统一用**子进程**跑 `alembic upgrade head`
- Dockerfile CMD 去掉 `alembic upgrade head`（迁移只在 `init_db` 做一次）

### 状态
- [x] 已解决（2026-06-17）

---

## 10. SSH / rsync 部署脚本报错 [network]

### 现象
| 报错 | 处理 |
|------|------|
| `.ssh/mac_bob.pem: Permission denied` | `chmod 600 ~/.ssh/mac_bob.pem` |
| `scp: stat local "22"` | `-P 22` 须在 `-i` 之前：`scp -P 22 -i key.pem ...` |
| `rsync invalid modifier sequence at 'g' in filter rule: .git/` | macOS rsync 2.6.9 兼容问题，改用 `.rsyncignore` |

### 状态
- [x] 已解决（2026-06-16）

---

## 11. Nginx 配置冲突与 404 [nginx]

### 现象
- `curl http://127.0.0.1/api/v1/health` 返回 Nginx 404（Ubuntu 默认页）
- `duplicate default server for 0.0.0.0:80 in sites-enabled/default`

### 原因
系统默认站点与 `poetry-agent` 配置同时监听 80。

### 解决方案
```bash
sudo rm /etc/nginx/sites-enabled/default
sudo ln -sf /etc/nginx/sites-available/poetry-agent /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```
或重跑 `./scripts/deploy/setup-ecs.sh`。

### 状态
- [x] 已解决（2026-06-16）

---

## 12. 其他常见运维问题

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 502 Bad Gateway | 容器未启动或 8000 未监听 | `remote-compose.sh logs` |
| 外网无法访问 | 安全组未放行 80 | 阿里云安全组入站放行 80、22 |
| Nginx 502 | nginx 未运行 | `systemctl start nginx` 或 `./scripts/deploy/setup-ecs.sh` |
| HuggingFace 模型下载慢/失败 | 国内网络 | `.env` / `.env.prod` 设 `HF_ENDPOINT=https://hf-mirror.com` |
| LangSmith 追踪混乱 | dev/prod 同一 project | dev 用 `poetry-agent-dev`，prod 用 `poetry-agent-prod` |
| LangSmith `403 Forbidden` | API Key 无效/过期、无写权限 | 见下方 **§12.1**；暂不需要追踪时 `LANGSMITH_TRACING=false` |
| `docker compose exec` 报 no configuration file | 不在项目目录 | 先 `cd /opt/poetry-agent` |
| 混合检索很慢（10s+） | 冷启动加载模型 | 预下载模型到 `data/models/`，生产同步 `--with-data` |
| ECS 查看 Postgres | PG 在 Docker 内 | `docker exec -it poetry-agent-postgres-1 psql -U poetry -d poetry_agent` |
| Redis `(unhealthy)` | AOF 损坏 / 磁盘满 / 仍在加载 | 见下方 **§13** |

---

## 12.1 LangSmith `403 Forbidden`（追踪上报失败）

### 现象

```text
WARNING langsmith.client - Failed to send compressed multipart ingest: ...
HTTPError('403 Client Error: Forbidden for url: https://api.smith.langchain.com/runs/multipart', ...)
```

### 说明

- **不影响**诗词对话、RAG、看图作诗等主功能，只是 LangSmith 后台看不到本次 Run 追踪。
- 出现条件：`.env` / `.env.prod` 中 `LANGSMITH_TRACING=true` 且配置了 `LANGSMITH_API_KEY`。

### 常见原因

1. API Key **已过期、被撤销或复制不完整**
2. Key 所属 LangSmith **工作区/账号**与 `LANGSMITH_PROJECT` 不匹配
3. 免费额度用尽或账号受限（较少见，通常仍表现为 403/401）

### 处理

**方案 A — 暂时关闭追踪（最快消除告警）**

```bash
# .env 或 .env.prod
LANGSMITH_TRACING=false
```

重启服务：`uvicorn` 本地重载，或 ECS 上 `docker compose restart app`。

**方案 B — 继续用追踪**

1. 登录 [smith.langchain.com](https://smith.langchain.com/settings) → Settings → API Keys
2. 新建 Personal Access Token，完整复制到 `LANGSMITH_API_KEY`（`lsv2_pt_...`）
3. 确认 `LANGSMITH_PROJECT` 名称（如 `poetry-agent-dev` / `poetry-agent-prod`）；首次写入会自动建项目
4. 重启应用，发一条 chat 请求，在 LangSmith 控制台确认 Run 出现

**验证 Key（可选）**

```bash
curl -s -o /dev/null -w "%{http_code}" \
  -H "x-api-key: $LANGSMITH_API_KEY" \
  https://api.smith.langchain.com/info
```

返回 `200` 表示 Key 有效；`403` 则需更换 Key。

---

## 13. Redis 容器 unhealthy

### 现象

```text
poetry-agent-redis-1   Up ... (unhealthy)   6379/tcp
```

`poetry-agent` 依赖 `redis: condition: service_healthy`，Redis 不健康时 **App 不会启动**。

### 诊断（SSH 到 ECS 后）

```bash
cd /opt/poetry-agent   # 或实际部署目录

# 健康检查详情（看 Last output）
docker inspect poetry-agent-redis-1 --format='{{range .State.Health.Log}}{{.Output}}{{end}}' | tail -5

docker compose logs redis --tail=80
docker compose exec redis redis-cli ping    # 期望 PONG；LOADING / 无响应则见下

df -h .
ls -la data/redis/
```

### 常见原因与处理

| 日志 / 现象 | 原因 | 处理 |
|-------------|------|------|
| `Bad file format reading the append only file` | AOF 损坏（异常断电等） | 见下方「修复 AOF」 |
| `redis-cli ping` → `LOADING` | AOF 较大，仍在载入 | 等待 1～5 分钟；仍失败则查日志 |
| `No space left on device` | 磁盘满 | `df -h` 清理空间后 `docker compose restart redis` |
| `Permission denied` on `/data` | `data/redis` 权限不对 | `sudo chown -R 999:999 data/redis` 后重启 |
| 日志无报错但 ping 失败 | Redis 进程已挂 | `docker compose restart redis`；仍失败则重建容器 |

#### 修复 AOF（会丢失未持久化的一小段写入，Checkpoint 可重建）

```bash
cd /opt/poetry-agent
docker compose stop redis
cp -a data/redis data/redis.bak.$(date +%Y%m%d)

docker run --rm -v "$(pwd)/data/redis:/data" redis:7-alpine \
  redis-check-aof --fix /data/appendonly.aof

docker compose up -d redis
docker compose exec redis redis-cli ping   # 确认 PONG
docker compose ps
```

---

## 推荐部署 checklist

- [ ] 本地：`.env`（dev）已配置
- [ ] 生产：`.env.prod` 已配置（独立 JWT、CORS、容器路径）
- [ ] `scripts/deploy/deploy.env` 已配置 ECS_HOST、POETRY_AGENT_IMAGE
- [ ] Dockerfile 基础镜像不走 docker.io（用阿里云代理或个人 ACR）
- [ ] ACR 控制台构建成功，镜像 tag 为 `:latest`
- [ ] ECS 已 `docker login` 个人 ACR
- [ ] 首次：`./scripts/deploy/deploy.sh --with-data`
- [ ] 日常：`./scripts/deploy/deploy.sh --pull`

---

## 关键文件索引

| 文件 | 作用 |
|------|------|
| `.env` | 本地开发环境变量 |
| `.env.prod` | ECS 生产环境变量（deploy 上传） |
| `scripts/deploy/deploy.env` | ECS SSH、ACR 镜像地址 |
| `docker-compose.dev.yml` | 本地 dev（可 build，`.env`） |
| `docker-compose.prod.yml` | ECS prod（只 pull ACR 镜像，`.env.prod`） |
| `Dockerfile` | ACR 云构建 / 备用本地 build |
| `scripts/deploy/deploy.sh` | 一键发布到 ECS |
| `docs/project-notes.md` | 通用问答自动记录 |
| `.cursor/skills/poetry-deploy-journal/SKILL.md` | Agent 自动保存问答到文档 |

---

## 2026-06-17 · Docker 构建是否会打包 .env.prod

**问**：`docker build` 会不会把生产环境配置（`.env.prod`）打进镜像？

**答**：会（修复前）。`.dockerignore` 原先只排除 `.env`，`Dockerfile` 里 `COPY . .` 会把本地存在的 `.env.prod` 一并复制进镜像层，存在密钥泄露风险。

生产运行时不受影响：`docker-compose.prod.yml` 通过 `env_file: .env.prod` 在 ECS 上挂载，`deploy.sh` 单独 scp 上传，不依赖镜像内配置。

**修复**：在 `.dockerignore` 增加 `.env.prod`（与 `.env`、`scripts/deploy/deploy.env` 一致）。

**标签**：`docker` | `config`

---

## 2026-06-17 · docker-compose dev / prod 分离

**问**：将 docker-compose 两个文件分离开，一个是 dev 一个是 prod。

**答**：不再使用「base + override」合并模式。现改为两个独立完整栈：

| 文件 | 场景 | 要点 |
|------|------|------|
| `docker-compose.dev.yml` | 本地开发 | `build: .`，`env_file: .env`，`APP_ENV=development` |
| `docker-compose.prod.yml` | ECS 生产 | ACR 镜像、`env_file: .env.prod`，`pull_policy: always` |

已删除原 `docker-compose.yml`。`remote-compose.sh` 按 `.compose.env` 中是否有 `POETRY_AGENT_IMAGE` 自动选 prod / dev 文件。

```bash
# 本地
docker compose -f docker-compose.dev.yml up --build

# ECS（或本地模拟 prod）
docker compose -f docker-compose.prod.yml up -d --no-build --pull always
```

**标签**：`docker` | `deploy` | `config`

---

## 2026-06-17 · 容器启动不再每次重建向量索引

**问**：不想每次启动都 rebuild index。

**答**：`Dockerfile` 原先 `CMD` 在 uvicorn 前执行 `build_index.py`（`force=True`），每次容器启动都会全量重建 Chroma，耗时长。

`app/main.py` lifespan 已调用 `build_vector_store()`：**有索引则加载，无索引才构建**。已从 `Dockerfile` 移除启动时 `build_index.py`。

需手动重建索引时：

```bash
docker compose -f docker-compose.dev.yml exec poetry-agent python scripts/build_index.py
# 或 ECS：./scripts/deploy/remote-compose.sh 登录后同样 exec
```

**标签**：`docker` | `rag`

---

## 2026-06-17 · 向量索引重建是否会重复入库

**问**：向量数据库重建索引是不是每次都是增加数据，然后有很多重复？

**答**：
- **正常启动**（`uvicorn` / 容器）：`build_vector_store()` 默认 `force=False`，`data/chroma_db` 已有数据则**只加载，不写入**，不会重复。
- **手动重建**（`python scripts/build_index.py`、语料上传/删除 API）：调用 `build_vector_store(force=True)`，当前实现**不会先清空**旧库，而是在已有 collection 上 `add_texts`，**会重复入库**（条数约翻倍）。
- **正确重建**：先删旧库再建索引：

```bash
rm -rf data/chroma_db
python scripts/build_index.py
```

**标签**：`rag`

**问**：`data/` 下文件属主混杂（`501 staff`、`1000:1000`、`70`、`lxd`），需要修正权限。

**答**：Mac `rsync --with-data` 会保留本地 uid `501`，而 `poetry-agent` 容器以 `uid 1000`（appuser）运行，无法写入 `chroma_db` / `sessions.db` 等。

| 路径 | 应有属主 | 说明 |
|------|----------|------|
| `corpus/`、`chroma_db/`、`models/`、`sessions.db`、`authors.json` | `1000:1000` | poetry-agent 容器 |
| `postgres/` | `70` | postgres:16-alpine |
| `redis/` | `999:999` | redis:7-alpine |

**一次性修复（SSH 登录 ECS）**：

```bash
cd /opt/poetry-agent
sudo ./scripts/deploy/fix-data-permissions.sh
# 或
sudo ./scripts/deploy/remote-compose.sh fix-perms
```

**后续部署**：`deploy.sh` 在每次 rsync 同步后自动执行 `fix-data-permissions.sh`（含普通发布与 `--env-only`）；`--with-data` 亦同。需 ECS SSH 用户为 root（`deploy.env` 默认 `ECS_USER=root`）。

**标签**：`deploy` | `docker` | `config`

---

## 2026-06-17 · Postgres checkpointer 回退 MemorySaver（缺 psycopg/libpq）

**问**：启动日志 `Postgres checkpointer unavailable, using memory: no pq wrapper available` / `libpq library not found`。

**答**：`langgraph-checkpoint-postgres` 依赖 **psycopg3**，但 `requirements.txt` 未安装带 libpq 的实现。`python:3.11-slim` 镜像也无系统 `libpq`。

**修复**：在 `requirements.txt` 增加：

```text
psycopg[binary]>=3.1.18,<4
```

`[binary]` 会安装预编译的 `psycopg_binary`，无需在 Dockerfile 里 apt 安装 `libpq`。

重建镜像并部署后，日志应出现 `Using Postgres checkpointer`。

**标签**：`docker` | `config` | `rag`

---

## 2026-06-17 · stream agent error：Embedding 加载失败（路径错误 + HF client closed）

**问**：聊天时报 `stream agent error`，堆栈在 `get_embeddings()` → `hf_hub_download`，最终 `RuntimeError: Cannot send a request, as the client has been closed`。

**答**：根因通常是 **`.env.prod` 中 `EMBEDDING_MODEL` 路径与 ECS 上 `data/models/` 实际目录名不一致**（如写成 `BAAI-bge-*` 单横线，而 `download_models.py` 生成的是 `BAAI--bge-*` 双横线）。本地目录找不到时，`sentence-transformers` 会尝试从 HuggingFace 拉取，容器内网络/镜像问题则表现为 `client has been closed`。

**排查**：

```bash
ls -la /opt/poetry-agent/data/models/
docker exec <poetry-agent容器> printenv EMBEDDING_MODEL
```

**修复**：

```bash
# .env.prod 与 download_models 输出一致
EMBEDDING_MODEL=./data/models/BAAI--bge-small-zh-v1.5
RERANK_MODEL=./data/models/BAAI--bge-reranker-base

./scripts/deploy/deploy.sh --env-only
# 若缺模型目录
python scripts/download_models.py && ./scripts/deploy/deploy.sh --with-data
```

代码侧：启动时 `warmup_rag_models()` 预加载 embedding / rerank；`resolve_model_path()` 只认本地目录，路径错误会在启动日志打印 `env=` / `resolved=` 并直接失败，不会回落 HuggingFace 远端。

**标签**：`deploy` | `rag` | `config`

---

## 2026-06-17 · 部署不同步 Postgres / Redis

**问**：`deploy.sh --with-data` 会不会把本地 Postgres / Redis 同步到 ECS，覆盖生产数据？

**答**：**不会，也不应同步。** 生产库只在 ECS 的 `data/postgres/`、`data/redis/` 维护。

| 机制 | 说明 |
|------|------|
| `.rsyncignore` | 排除 `data/postgres/`、`data/redis/`，主 rsync（含 `--delete`）永不碰这两目录 |
| `--with-data` | `_sync_data()` 仅同步语料、向量库、模型等，同样 `--exclude postgres/`、`--exclude redis/` |

日常发布：

```bash
./scripts/deploy/deploy.sh              # 只同步代码/配置，不动 data/
./scripts/deploy/deploy.sh --with-data  # 仅同步 chroma_db、models、corpus 等
```

**标签**：`deploy` | `docker` | `config`

---

## 2026-06-17 · Postgres UndefinedFileError（数据目录损坏）

**问**：应用报错 `asyncpg.exceptions.UndefinedFileError: could not open file "base/16384/16389": No such file or directory`。

**答**：这是 **PostgreSQL 数据文件损坏或缺失**，不是应用代码问题。`base/16384/` 是 `poetry_agent` 库的 OID 目录，`16389` 是某张表/索引的数据文件，磁盘上已不存在但 catalog 仍引用它。

**常见原因**：

| 原因 | 说明 |
|------|------|
| 磁盘满 | 写入中断导致文件不完整 |
| 权限错误 | `data/postgres` 属主不是 `70:70`，Postgres 无法正确读写 |
| 异常停机 | `kill -9`、ECS 强制重启、断电 |
| 误操作 | 手动删改 `data/postgres/` 内文件，或曾用 rsync 覆盖（本项目已排除，但仍需排查） |

**排查（SSH 登录 ECS）**：

```bash
cd /opt/poetry-agent

# 1. 磁盘空间
df -h .

# 2. postgres 目录权限（应为 70:70，chmod 700）
ls -la data/postgres/
sudo ./scripts/deploy/remote-compose.sh fix-perms

# 3. postgres 容器日志
docker compose -f docker-compose.prod.yml logs postgres --tail=50

# 4. 尝试连库（若也失败则确认损坏）
docker exec -it poetry-agent-postgres-1 psql -U poetry -d poetry_agent -c '\dt'
```

**修复 A — 可接受丢数据（最常见）**：

会话/消息可重建时，清空 Postgres 数据目录并重新初始化：

```bash
cd /opt/poetry-agent
docker compose -f docker-compose.prod.yml down

# 备份损坏目录（可选）
sudo mv data/postgres data/postgres.bak.$(date +%Y%m%d)

# 重建空库
sudo mkdir -p data/postgres
sudo chown -R 70:70 data/postgres
sudo chmod 700 data/postgres

docker compose -f docker-compose.prod.yml up -d
# 启动后 poetry-agent 会自动 alembic upgrade head
```

**修复 B — 需保留数据**：

若曾做过 `pg_dump` 备份，恢复备份；否则只能尝试 `pg_resetwal` / 专业恢复工具，成功率低。**生产环境应定期备份**：

```bash
docker exec poetry-agent-postgres-1 pg_dump -U poetry poetry_agent > backup.sql
```

**预防**：

- 部署脚本已排除 `data/postgres/`，不要用 `--with-data` 或 rsync 覆盖生产库
- 定期 `pg_dump`；ECS 磁盘告警
- 权限：`fix-data-permissions.sh` 只改 `postgres/` 为 uid `70`

**标签**：`deploy` | `docker` | `config`

---

## 2026-06-17 · 生产 compose 显式挂载 models

**问**：`docker-compose.prod.yml` 没有把模型目录映射进容器。

**答**：原先仅 `./data:/app/data` 整目录挂载，models 虽在其中但不直观，且 `.env.prod` 用相对路径 `./data/models/...` 与 `CHROMA_PERSIST_DIR=/app/data/...` 不一致。

**修复**（`docker-compose.prod.yml`）：

```yaml
volumes:
  - ./data/models:/app/data/models:ro
  - ./data/corpus:/app/data/corpus
  - ./data/chroma_db:/app/data/chroma_db
  - ./data:/app/data
```

`.env.prod` 中模型路径改为容器绝对路径，例如：

```bash
EMBEDDING_MODEL=/app/data/models/bge-small-zh-v1.5
RERANK_MODEL=/app/data/models/bge-reranker-base
```

**同步模型到 ECS**（首次或更新模型）：

```bash
python scripts/download_models.py
./scripts/deploy/deploy.sh --with-data
./scripts/deploy/deploy.sh --env-only   # 上传 .env.prod
# ECS 上重建容器
ssh ecs 'cd /opt/poetry-agent && ./scripts/deploy/remote-compose.sh recreate'
```

**校验**：

```bash
docker exec poetry-agent-poetry-agent-1 ls -la /app/data/models/
docker exec poetry-agent-poetry-agent-1 printenv EMBEDDING_MODEL
```

**标签**：`deploy` | `docker` | `config`

---

## 2026-06-17 · 容器内 models 为空（本地未同步）

**问**：compose 已配置 `./data/models:/app/data/models:ro`，容器内仍看不到模型。

**答**：挂载只映射**宿主机已有文件**；ECS 上 `data/models/` 为空时，容器内也是空的（bind mount 会遮盖镜像内同路径内容）。普通 `deploy.sh` **不会**同步 models——`.rsyncignore` 排除了 `data/models/`（体积大，避免每次发布都传）。

**同步模型到 ECS**：

```bash
# 本地先确认有模型
ls data/models/

# 方式 1：仅同步 models（推荐，最快）
./scripts/deploy/deploy.sh --models-only

# 方式 2：同步全部 data（含 chroma_db、corpus、models）
./scripts/deploy/deploy.sh --with-data

# 方式 3：发布代码同时带 models
./scripts/deploy/deploy.sh --with-models
```

**`.env.prod` 路径须与 ECS 上实际目录名一致**（本机示例）：

```bash
EMBEDDING_MODEL=/app/data/models/bge-small-zh-v1.5
RERANK_MODEL=/app/data/models/BAAI--bge-reranker-base
```

**校验**：

```bash
# ECS 宿主机
ls -la /opt/poetry-agent/data/models/

# 容器内
docker exec poetry-agent-poetry-agent-1 ls -la /app/data/models/
```

**标签**：`deploy` | `docker` | `rag`

---

## 2026-06-17 · deploy 同步后自动 fix-data-permissions

**问**：为什么 deploy 同步之后不马上执行 `fix-data-permissions.sh`？

**答**：原先逻辑有疏漏——仅在 `--with-data` 的 `_sync_data()` 末尾调用；普通 `./scripts/deploy/deploy.sh`（只 rsync 代码）不会修正权限，可能导致 postgres（uid 70）、app（uid 1000）读写失败。

**现行为**：任意 rsync 同步完成后、启动/重建容器**之前**，统一执行：

```bash
_fix_app_data_permissions   # 远端 fix-data-permissions.sh
```

覆盖：`deploy.sh`（默认）、`--with-data`、`--env-only`。`--pull` 不同步文件，不触发。

**标签**：`deploy` | `docker` | `config`

---

## 2026-06-17 · 查询容器/镜像构建参数

**问**：如何查询容器 `93c587dbc07b` 的构建参数？

**答**：Docker **不会把 `ARG` 构建参数存进容器**；只能查容器运行配置，或从镜像元数据间接推断。

**1. 容器基本信息（镜像 ID、环境变量、挂载等）**：

```bash
docker inspect 93c587dbc07b
docker inspect --format='镜像: {{.Config.Image}}
创建: {{.Created}}
Env: {{range .Config.Env}}{{.}}
{{end}}' 93c587dbc07b
```

**2. 从容器反查镜像，再看镜像层与标签**：

```bash
IMAGE=$(docker inspect --format='{{.Config.Image}}' 93c587dbc07b)
docker image inspect "$IMAGE"
docker history --no-trunc "$IMAGE"
```

**3. 本项目 Dockerfile 的 ARG（默认值，构建时可覆盖）**：

| ARG | 默认值 |
|-----|--------|
| `NODE_IMAGE` | `docker.m.daocloud.io/library/node:20-slim` |
| `PYTHON_IMAGE` | `docker.m.daocloud.io/library/python:3.11-slim` |
| `TORCH_CPU_VERSION` | `2.5.1` |

ACR 云构建若在控制台传了 build-arg，以 **ACR 构建记录** 为准，容器内查不到。

**4. ECS 上查 poetry-agent 容器**：

```bash
docker ps -a | grep poetry
docker inspect poetry-agent-poetry-agent-1
docker inspect --format='{{.Config.Image}}' poetry-agent-poetry-agent-1
```

**标签**：`deploy` | `docker`

---

## 2026-06-17 · deploy.sh 恢复 fix-data-permissions

**问**：发布脚本 `deploy.sh` 被注释掉权限修复，与文档不一致。

**答**：`save local` 提交误将 `_fix_app_data_permissions` 整段注释。已恢复，并在 `--models-only` 路径增加 `_sync_compose_config`（确保 models 卷挂载配置同步到 ECS）。

| 命令 | fix-perms | 说明 |
|------|-----------|------|
| `deploy.sh`（默认） | ✅ rsync 后 | 远端无 `data/` 时自动跳过 |
| `--with-data` / `--with-models` | ✅ | 同步 data 后执行 |
| `--models-only` | ✅ | 同步 compose + models 后执行 |
| `--env-only` | ✅ | recreate 前执行 |
| `--pull` | ❌ | 无文件同步 |

**标签**：`deploy` | `docker` | `config`

---

## 2026-06-17 · macOS rsync 不支持 --chown

**问**：本地执行 `deploy.sh --models-only` 报错 `rsync: --chown=1000:1000: unknown option`（client=2.6.9）。

**答**：macOS 自带 rsync 2.6.9 无 `--chown`（需 3.1+）。已从 `deploy.sh` 的 `_sync_data` / `_sync_models` 移除该选项；同步完成后由远端 `fix-data-permissions.sh` 统一修正属主（app=1000, postgres=70, redis=999）。

```bash
./scripts/deploy/deploy.sh --models-only   # 同步后自动 fix-perms
```

若需新版 rsync：`brew install rsync`（可选，非必须）。

**标签**：`deploy` | `docker` | `config`

---

## 2026-06-17 · SSH 本地端口转发访问 ECS

**问**：如何把本地 `localhost:3000` 转发到 ECS `8.134.168.40:80`？

**答**：SSH 本地转发（`-L`），将本机 3000 映射到 ECS 上 nginx 的 80：

```bash
# 前台（终端保持打开）
ssh -N -L 3000:127.0.0.1:80 -p 22 -i ~/.ssh/mac_bob.pem root@8.134.168.40

# 后台
ssh -f -N -L 3000:127.0.0.1:80 -p 22 -i ~/.ssh/mac_bob.pem root@8.134.168.40
```

浏览器访问：`http://localhost:3000/`

关闭隧道：

```bash
# 查 PID 并结束
pgrep -fl 'ssh.*3000:127.0.0.1:80'
kill <PID>
```

**标签**：`deploy` | `config`

---

## 2026-06-18 · Certbot 为 cnpoetry.top 配置 HTTPS

**问**：如何用 Certbot（Let's Encrypt）为 `cnpoetry.top` 配置 HTTPS（Ubuntu ECS）？

**答**：

**1. 前置**

| 项 | 说明 |
|----|------|
| DNS | `cnpoetry.top`、`www.cnpoetry.top` A 记录 → ECS 公网 IP（如 `8.134.168.40`） |
| 安全组 | 放行 **80**、**443** |
| 服务 | `curl http://127.0.0.1/api/v1/health` 已返回 ok |

**2. 本地一键（推荐）**

在 `scripts/deploy/deploy.env` 增加：

```bash
DOMAIN=cnpoetry.top
CERTBOT_EMAIL=your-email@example.com
INCLUDE_WWW=true
```

```bash
./scripts/deploy/setup-ssl-certbot.sh          # 申请并配置 HTTPS
./scripts/deploy/setup-ssl-certbot.sh --dry-run # 仅检查 DNS/nginx
```

**3. ECS 上手动（Ubuntu）**

```bash
# 安装 Certbot nginx 插件
sudo apt update
sudo apt install -y certbot python3-certbot-nginx

# 确保 nginx server_name 含域名（见 scripts/deploy/nginx/poetry-agent.domain.conf）
sudo nginx -t && sudo systemctl reload nginx

# 申请证书（自动改 nginx、开启 443、HTTP→HTTPS 跳转）
sudo certbot --nginx -d cnpoetry.top -d www.cnpoetry.top

# 验证
curl -sf https://cnpoetry.top/api/v1/health
sudo certbot certificates
sudo systemctl status certbot.timer   # 自动续期
```

**4. 更新应用 CORS**

`.env.prod`：

```bash
CORS_ORIGINS=https://cnpoetry.top,https://www.cnpoetry.top
```

```bash
./scripts/deploy/deploy.sh --env-only
```

**标签**：`deploy` | `nginx` | `config`
