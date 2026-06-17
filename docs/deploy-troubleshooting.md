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
| `docker compose exec` 报 no configuration file | 不在项目目录 | 先 `cd /opt/poetry-agent` |
| 混合检索很慢（10s+） | 冷启动加载模型 | 预下载模型到 `data/models/`，生产同步 `--with-data` |
| ECS 查看 Postgres | PG 在 Docker 内 | `docker exec -it poetry-agent-postgres-1 psql -U poetry -d poetry_agent` |
| Redis `(unhealthy)` | AOF 损坏 / 磁盘满 / 仍在加载 | 见下方 **§13** |

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

## 2026-06-17 · ECS data/ 目录权限混乱（501 vs 1000）

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

**后续部署**：`deploy.sh --with-data` 已自动 `rsync --chown=1000:1000`（排除 postgres/redis）并执行权限修复。

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
