# 古典诗词鉴赏智能助手

> 个人学习项目 · 诗词知识库 RAG + LangGraph 多轮 Agent + 工具链

## 项目定位

面向古典诗词鉴赏场景，串联 **LangChain、LangGraph、RAG、Chroma、混合检索、Rerank、Function Calling、Prompt 工程、FastAPI、Docker** 的练手与面试演示项目。

## 架构一览

```
用户（React + JWT）
    ↓
FastAPI (/api/v1/chat/stream)
    ├─ JWT 认证 + 套餐配额
    ├─ 会话/消息持久化（PostgreSQL / 本地 SQLite）
    └─ LangGraph Agent
        ├─ 意图识别（规则 + LLM）
        ├─ 高置信 RAG 快路径 / 工具有限 ReAct（多轮 + poetry_search）
        ├─ 低置信度 → ReAct 兜底
        └─ 闲聊分支
    ↓
多轮记忆（thread_id + LangGraph Checkpoint：Postgres → Redis → MemorySaver 降级）
    ↓
可观测性（LangSmith / Prometheus / Sentry）
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.11 + FastAPI + SQLAlchemy 2.0 异步 |
| 前端 | React 19 + Vite + shadcn/ui + Tailwind + AuthContext |
| 认证 | JWT（access + refresh）+ 多租户配额 |
| 数据 | PostgreSQL 16 + Alembic 迁移（本地 Docker 或 ECS） |
| 缓存/Checkpoint | Redis 7（Agent 记忆 + 限流计数） |
| 会话 | 数据库持久化 + SSE 流式输出 |
| Agent | LangChain + LangGraph |
| RAG | BGE-small-zh Embedding + Chroma + BM25 混合检索 + BGE-Rerank |
| 工具 | 作者生平 / 格律分析 / 风格对比 / 主题推荐等 7 个工具 |
| LLM | 通义千问（DashScope OpenAI 兼容 API，默认 `qwen-plus`） |
| 可观测 | LangSmith 追踪、Prometheus `/metrics`、Sentry、Token 用量计量 |
| 部署 | Docker Compose（Postgres + Redis + App） |

### 本地开发 vs 全栈 Docker

| 配置项 | 本地开发（推荐） | 全栈 Docker / ECS |
|--------|------------------|---------------------|
| Postgres / Redis | `docker compose -f docker-compose.infra.yml up -d` | 随 compose 栈一起启动 |
| 应用进程 | 宿主机 `uvicorn --reload` | 容器内运行 |
| 数据库连接 | `localhost:5432` / `6379`（见 `.env.example`） | 服务名 `postgres` / `redis` |
| Schema | 启动时自动 `alembic upgrade head` | 同上 |
| Agent 记忆 | Postgres / Redis Checkpoint | 同上 |
| 限流 | Redis（`RATE_LIMIT_STORAGE_URI`） | 同上 |
| 向量库 | 本地 `data/chroma_db` | 挂载 `./data` 卷 |

> **说明**：不配 `DATABASE_URL` / `REDIS_URL` 时仍可降级为 SQLite + MemorySaver；默认 `.env.example` 已指向 Docker 基础设施，与生产行为一致。

## 快速开始

### 1. 环境准备

**请使用 Python 3.11 或 3.12**。当前 PyTorch 尚未为 **Python 3.13** 提供 macOS/Windows 等平台的预编译包，`sentence-transformers` 会因此无法安装。项目根目录已提供 `.python-version`（pyenv 用户可直接 `pyenv install`）。

```bash
cd poetryAgent
python3.11 -m venv .venv   # 必须用 3.11/3.12，勿用系统默认 python3（可能是 3.13）
source .venv/bin/activate   # Windows: .venv\Scripts\activate
python --version            # 应显示 3.11.x 或 3.12.x

# 国内网络建议加镜像与更长超时（torch 包较大）
pip install -r requirements.txt \
  -i https://pypi.tuna.tsinghua.edu.cn/simple \
  --default-timeout=120

cp .env.example .env
# 编辑 .env，填入 DashScope API Key（OPENAI_API_KEY）
# 可选模型：qwen-turbo / qwen-plus / qwen-max
```

#### 依赖安装失败排查

| 报错 | 原因 | 处理 |
|------|------|------|
| `No matching distribution found for torch` | 使用了 **Python 3.13** | 删除旧 venv，用 `python3.11 -m venv .venv` 重建 |
| `Read timed out` / 连接 pypi.org 超时 | 网络慢或需镜像 | 加 `-i https://pypi.tuna.tsinghua.edu.cn/simple --default-timeout=120` |
| `Requires-Python <3.13` | 同上，3.13 不兼容 | 切换到 3.11/3.12 |

```bash
# 一键重建环境（推荐）
rm -rf .venv
python3.11 -m venv .venv && source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --default-timeout=120
```

### 2. 构建向量库

```bash
python scripts/build_index.py
```

首次运行会下载 `BAAI/bge-small-zh-v1.5` 与 `BAAI/bge-reranker-base`（需网络）。

**浏览器能打开 [HF-Mirror](https://hf-mirror.com)，但 Python 仍连不上 `huggingface.co` 时**（常见）：

1. 确认 `.env` 中有 `HF_ENDPOINT=https://hf-mirror.com`
2. 用专用脚本经镜像**预下载到本地**（最稳妥）：

```bash
python scripts/download_models.py
# 按脚本输出，把 EMBEDDING_MODEL / RERANK_MODEL 改为 data/models/... 本地路径
python scripts/build_index.py
```

3. 若仍失败，检查终端是否设置了错误代理（与浏览器不一致）：

```bash
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy
export HF_ENDPOINT=https://hf-mirror.com
python scripts/download_models.py
```

4. 或使用 [HF-Mirror 文档](https://hf-mirror.com) 中的 `huggingface-cli download`，下载后把 `.env` 里模型改为本地目录绝对路径。

### 3. 启动 Postgres + Redis（Docker）

```bash
docker compose -f docker-compose.infra.yml up -d
docker compose -f docker-compose.infra.yml ps   # 确认 healthy
```

数据持久化在 `./data/postgres` 与 `./data/redis`。停止：`docker compose -f docker-compose.infra.yml down`（不加 `-v`，数据保留）。

### 4. 启动后端

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

首次连接 Postgres 时会自动执行 Alembic 迁移。

访问 http://localhost:8000/docs 查看 Swagger API。

### 5. 启动前端（开发模式）

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 http://localhost:5173 。Vite 会将 `/api` 代理到后端 `8000` 端口。

**前端功能**：会话侧边栏（新建 / 列表 / 搜索 / 重命名 / 删除）、SSE 流式输出、Markdown 渲染、多行输入（Shift+Enter 换行）、字数限制、停止生成、深色模式、**看图作诗**（上传图片触发创作）。

### 看图作诗

在聊天输入框点击「图片」上传 JPEG / PNG / WebP（最大 4MB），可仅传图或附加文字说明体裁与主题。

**流程**：视觉模型（默认 `qwen-vl-max`）理解画面意境 → 合成描述后走现有创作 Agent（`qwen-plus` + `writing_assistant`）→ 流式输出诗作。

| 配置项 | 说明 |
|--------|------|
| `VISION_MODEL` | 视觉模型，默认 `qwen-vl-max` |
| `OPENAI_API_KEY` | 与文本 LLM 共用 DashScope API Key |

- 仅上传图片、无文字时，默认创作 **五言绝句**
- 图片**不持久化**；会话历史中保存的是画面描述文字，刷新后不可回看原图
- 每次看图作诗会调用两次 LLM（视觉描述 + 诗词创作），请注意 API 用量

### 6. 生产构建（前后端一体）

```bash
cd frontend && npm run build && cd ..
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

构建后访问 http://localhost:8000 即为聊天界面，API 仍在 `/api/v1`。

### 7. Docker 全栈（App + Postgres + Redis）

```bash
docker compose -f docker-compose.dev.yml up --build
```

Compose 栈包含 **PostgreSQL + Redis + App**，启动时自动执行 `alembic upgrade head` 并完成数据库迁移。访问 http://localhost:8000（需先构建前端或挂载 dist）。

### 8. 测试

```bash
# 需先 pip install -r requirements.txt
pytest tests/ -v
pytest tests/ -v --cov=app --cov-fail-under=40   # 与 CI 一致
```

测试覆盖：JWT 认证、输入安全、意图规则、会话 CRUD、Chat/RAG API（Mock LLM，不消耗 API Key）。

### 9. RAG 检索评估

**简易关键词检查**（无需 LLM API）：

```bash
python scripts/eval_rag.py
python scripts/eval_rag.py --golden tests/eval/rag_golden_set.json
```

**Ragas 全链路评估**（检索 + 生成 + 多维度指标，需 `OPENAI_API_KEY`）：

```bash
pip install -r requirements-eval.txt \
  -i https://pypi.tuna.tsinghua.edu.cn/simple --default-timeout=120
python scripts/eval_rag_ragas.py
python scripts/eval_rag_ragas.py --retrieval-only   # 仅评检索（ContextRecall）
python scripts/eval_rag_ragas.py --output reports/ragas.json
```

| 脚本 | 指标 | 说明 |
|------|------|------|
| `eval_rag.py` | 召回数、关键词命中 | 离线 smoke test，适合 CI |
| `eval_rag_ragas.py` | Faithfulness、AnswerRelevancy、ContextRecall、FactualCorrectness | 基于 [Ragas](https://docs.ragas.io/)，用 LLM 评判回答质量 |

Golden set 位于 `tests/eval/rag_golden_set.json`，每条含 `query`、`reference`（参考答案）及可选 `author` 过滤。

### 10. 部署到阿里云 ECS

通过 SSH + rsync 将项目同步到 ECS，在远端 `docker compose build` 启动；Nginx 监听 80 端口反代到容器 `8000`。

**推荐 ECS 规格**：2 vCPU / 4 GiB 内存起，系统盘 ≥ 40 GB（需加载 PyTorch 与 BGE 模型）。安全组入站放行 **22**（SSH）、**80**（HTTP）。

#### 一次性初始化 ECS

```bash
cp scripts/deploy/deploy.env.example scripts/deploy/deploy.env
# 编辑 deploy.env：ECS_HOST、SSH_KEY、REMOTE_DIR 等
./scripts/deploy/setup-ecs.sh
```

`setup-ecs.sh` 会在 ECS 上安装 Docker、Nginx，并写入反向代理配置（含 SSE 流式支持）。

#### 配置环境变量（dev / prod 隔离）

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
CORS_ORIGINS=http://<ECS公网IP>,https://<你的域名>
```

#### 首次发布

应用依赖 Embedding/Rerank 模型与向量库，首次部署二选一：

- **推荐（本地已构建好）**：本地执行 `python scripts/download_models.py` 与 `python scripts/build_index.py`，再同步数据发布：

```bash
./scripts/deploy/deploy.sh --with-data
```

- **在 ECS 构建**：先 `./scripts/deploy/deploy.sh`，SSH 登录后进入容器下载模型并建索引（耗时较长，需 ECS 内存 ≥ 4GB）。

#### 日常更新

```bash
./scripts/deploy/deploy.sh              # 同步配置并启动（ACR 模式只 pull，不 build）
./scripts/deploy/deploy.sh --with-data  # 同步 data/（语料、模型、向量库）
./scripts/deploy/deploy.sh --env-only   # 仅更新 .env.prod 并重启
./scripts/deploy/deploy.sh --pull       # 仅拉取最新 ACR 镜像并重启
```

#### 推荐：阿里云 ACR 部署（避免 ECS 运行时 build）

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

#### 日常更新（ECS 本地 build 方式）

```bash
./scripts/deploy/deploy.sh              # 同步代码并在 ECS build（较慢）
./scripts/deploy/deploy.sh --env-only   # 仅更新 .env.prod 并重启
```

部署成功后访问 `http://<ECS公网IP>/`。

#### 远端运维

SSH 登录 ECS 后，在项目目录执行：

```bash
cd /opt/poetry-agent   # 或 deploy.env 中的 REMOTE_DIR
./scripts/deploy/remote-compose.sh logs
./scripts/deploy/remote-compose.sh health
./scripts/deploy/remote-compose.sh restart
```

#### 故障排查

| 现象 | 处理 |
|------|------|
| 502 Bad Gateway | 容器未启动 → `remote-compose.sh logs` |
| RAG 无检索结果 | `data/chroma_db` 未同步或未建索引 → `deploy.sh --with-data` 或容器内执行 `build_index.py` |
| 模型下载失败 | 确认 `.env.prod` 中 `HF_ENDPOINT=https://hf-mirror.com`；ECS 安全组出站放行 HTTPS |

## 可观测性（LangSmith）

项目已集成 [LangSmith](https://smith.langchain.com/)，用于追踪 Agent 全链路：API 根 Run → 意图识别 → RAG/工具 → LLM 流式生成。

### 启用方式

在 `.env` 中配置（参见 `.env.example`）：

| 变量 | 说明 |
|------|------|
| `LANGSMITH_API_KEY` | [LangSmith API Key](https://smith.langchain.com/settings) |
| `LANGSMITH_TRACING` | 设为 `true` 启用追踪 |
| `LANGSMITH_PROJECT` | 项目名，默认 `poetry-agent`；可用 `poetry-agent-dev` / `poetry-agent-prod` 区分环境 |

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_pt_...
LANGSMITH_PROJECT=poetry-agent-dev
```

重启后端后，在 LangSmith UI 的对应 Project 中即可看到每次 `/chat`、`/chat/stream`、`/rag`、`/tools/*` 的 Run 树。

### Run 树结构

```
chat_request（根）
├── prepare_agent
│   ├── classify_intent（metadata: intent_source, final_intent）
│   ├── retrieve_rag / prepare_tool_call + run_tools
│   └── hybrid_retrieve（metadata: doc_count, top_scores）
└── stream_final_answer / collect_stream（metadata: ttft_ms, mode）
```

可按 tag `session_id:<uuid>` 过滤同一会话的多轮对话。

### 推荐监控指标

在 LangSmith Dashboard 中可按 metadata 聚合以下指标：

| 优先级 | 指标 | metadata / 字段 |
|--------|------|-----------------|
| P0 | E2E 延迟 p50/p95 | 根 Run `latency` |
| P0 | 流式 TTFT | `ttft_ms` |
| P0 | 错误率 | Run `status=error` |
| P0 | Token 用量 / 成本 | LLM Run 自动记录 |
| P1 | 意图分布 | `intent` |
| P1 | 规则命中率 | `intent_source=rule` |
| P1 | RAG 空召回率 | `doc_count=0` |
| P1 | 工具成功率 | `tool_results` |
| P2 | 每会话轮数 | tag `session_id:*` |

建议创建三个视图：**Ops**（延迟/错误）、**Cost**（Token/意图分组）、**Quality**（意图分布/空召回/工具错误）。

## API 示例

### 流式对话（SSE）

```bash
curl -N -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "请赏析《登高》", "session_id": "<uuid>"}'
```

事件类型：`status`（阶段）→ `token`（逐字）→ `done`（完成）。

### 会话管理

```bash
# 新建会话
curl -X POST http://localhost:8000/api/v1/sessions

# 列表 / 搜索
curl "http://localhost:8000/api/v1/sessions?q=登高"

# 重命名
curl -X PATCH http://localhost:8000/api/v1/sessions/<id> \
  -H "Content-Type: application/json" -d '{"title": "杜甫登高赏析"}'

# 删除
curl -X DELETE http://localhost:8000/api/v1/sessions/<id>
```

### 诗词鉴赏（Agent 自动走 RAG，非流式）

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "请赏析《登高》", "thread_id": "user-1"}'
```

### 多轮追问（同一 thread_id）

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "这首诗的名句有哪些？", "thread_id": "user-1"}'
```

### 作者生平

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "介绍杜甫"}'
```

### 格律分析

```bash
curl -X POST http://localhost:8000/api/v1/tools/meter \
  -H "Content-Type: application/json" \
  -d '{"title": "静夜思"}'
```

### 风格对比

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "李白和杜甫的诗歌风格有什么区别？"}'
```

### 纯 RAG 检索

```bash
curl -X POST http://localhost:8000/api/v1/rag \
  -H "Content-Type: application/json" \
  -d '{"query": "表达思乡的诗", "author": "李白"}'
```

## 目录结构

```
poetryAgent/
├── app/
│   ├── main.py           # FastAPI 入口（含 StaticFiles 挂载）
│   ├── config.py         # 配置
│   ├── observability/    # LangSmith 追踪
│   ├── db/               # SQLAlchemy 模型 + Alembic 迁移
│   ├── auth/             # JWT 认证、配额
│   ├── api/              # 路由与 Schema
│   ├── rag/              # 分块、Embedding、混合检索、Rerank
│   ├── agent/            # LangGraph 工作流、Prompt、工具绑定
│   ├── tools/            # 作者/格律/对比
│   └── security/         # 输入过滤
├── frontend/             # React 聊天 UI（Vite + shadcn/ui）
│   └── src/
│       ├── components/   # SessionSidebar、MessageList、ChatInput
│       ├── hooks/        # useSessions、useChatStream
│       └── api/          # REST + SSE 客户端
├── data/
│   ├── corpus/           # 诗词 Markdown 语料
│   ├── authors.json      # 作者库
│   └── chroma_db/        # 向量库（构建后生成）
├── alembic/              # 数据库迁移（001_initial_schema）
├── tests/                # pytest（auth / 安全 / 意图 / API 集成）
│   └── eval/             # RAG golden set
├── scripts/
│   ├── build_index.py       # 构建 / 重建向量索引
│   ├── eval_rag.py          # RAG 检索关键词评估（离线）
│   ├── eval_rag_ragas.py    # Ragas 全链路 RAG 评估
│   ├── generate_corpus.py   # LLM 批量生成语料
│   └── deploy/              # 阿里云 ECS 部署脚本
│       ├── deploy.sh
│       ├── setup-ecs.sh
│       └── remote-compose.sh
├── Dockerfile
├── docker-compose.dev.yml   # 本地开发（build + .env）
└── docker-compose.prod.yml  # ECS 生产（ACR pull + .env.prod）
```

## LLM 批量生成语料

使用 `scripts/generate_corpus.py`，通过通义千问（DashScope）调用 LLM，将结构化 Markdown 写入 `data/corpus/`。

### 前置配置

在 `.env` 中配置（参见 `.env.example`）：

| 变量 | 说明 |
|------|------|
| `OPENAI_API_KEY` | [DashScope API Key](https://dashscope.console.aliyun.com/) |
| `OPENAI_API_BASE` | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `LLM_MODEL` | 默认 `qwen-plus`；可选 `qwen-turbo`、`qwen-max` |

### 推荐：`auto`（无需指定诗名）

由 LLM 从唐宋著名作品中自动选题，再逐首生成语料。**只需指定篇数**，默认 **20 篇**：

```bash
# 默认生成 20 篇，并重建向量索引（推荐一条龙）
python scripts/generate_corpus.py auto --rebuild-index

# 指定篇数
python scripts/generate_corpus.py auto --count 10 --rebuild-index

# 仅预览选题列表，不写文件
python scripts/generate_corpus.py auto --count 5 --dry-run
```

### 其他生成方式

| 子命令 | 适用场景 | 示例 |
|--------|----------|------|
| `single` | 已知诗题、作者，生成单篇 | `python scripts/generate_corpus.py single --title 春望 --author 杜甫 --dynasty 唐 --genre 七言律诗` |
| `batch` | 任务列表 / 文件批量，需指定诗名 | `python scripts/generate_corpus.py batch -f data/poems_batch.example.txt` |
| `theme` | 按主题选题（默认 5 篇） | `python scripts/generate_corpus.py theme --theme 思乡 --count 5` |
| `dynasty` | 按朝代选题（默认 5 篇） | `python scripts/generate_corpus.py dynasty --dynasty 宋 --count 5` |
| `author` | 生成作者资料到 `authors.json` | `python scripts/generate_corpus.py author --name 王维` |

`batch` 补充示例：

```bash
# 命令行多条（诗题,作者[,朝代][,体裁]）
python scripts/generate_corpus.py batch -i "使至塞上,王维,唐,五言律诗" "枫桥夜泊,张继,唐,七言绝句"

# 任务文件（见 data/poems_batch.example.txt），# 开头为注释
python scripts/generate_corpus.py batch --file data/poems_batch.example.txt --rebuild-index
```

### 通用参数

以下参数适用于 `single` / `batch` / `theme` / `dynasty` / `auto`（`author` 仅支持 `--force`）：

| 参数 | 说明 |
|------|------|
| `--count N` | 选题类命令的篇数（`auto` 默认 20，`theme`/`dynasty` 默认 5） |
| `--rebuild-index` | 完成后自动执行 `scripts/build_index.py` 重建向量库 |
| `--dry-run` | 仅选题预览或校验，不写入 `data/corpus/` |
| `--force` | 覆盖已存在的语料文件 |
| `--delay 1.0` | 批量请求间隔（秒），默认 1 |
| `--no-skip` | 不跳过已存在文件（遇同名则报错） |

生成流程简述：`auto` / `theme` / `dynasty` 先由 LLM 输出 JSON 选题列表，再逐首生成含原文、注释、译文、鉴赏的 Markdown；已存在 `诗题-作者.md` 时默认跳过。

## 扩展语料（手动）

在 `data/corpus/` 新增 Markdown，标题格式建议：

```markdown
# 《诗题》-作者-朝代-体裁

## 原文
...

## 鉴赏
...

## 元数据
- 作者：李白
- 朝代：唐
```

然后重新执行 `python scripts/build_index.py`。

## 面试可讲要点

1. **分块策略**：按单首诗词+鉴赏为语义块，100 token 重叠防断裂，标题锚定元数据。
2. **混合检索**：向量语义 + BM25 关键词，合并去重后 BGE-Rerank 精排。
3. **LangGraph**：意图分支、RAG/工具/闲聊三路、Checkpoint 多轮记忆（Postgres/Redis）。
4. **幻觉抑制**：系统 Prompt 约束 + 强制引用 [1][2] + 无资料时明确说明。
5. **工程化**：JWT 多租户、Alembic 迁移、FastAPI 异步、Token 计量、Docker 一键部署、pytest CI。

## 许可证

MIT · 学习用途
