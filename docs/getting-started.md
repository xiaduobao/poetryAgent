# 本地开发指南

> 返回 [文档首页](README.md)

## 1. 环境准备

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

### 依赖安装失败排查

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

## 2. 构建向量库

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

## 3. 启动 Postgres + Redis（Docker）

```bash
docker compose -f docker-compose.infra.yml up -d
docker compose -f docker-compose.infra.yml ps   # 确认 healthy
```

数据持久化在 `./data/postgres` 与 `./data/redis`。停止：`docker compose -f docker-compose.infra.yml down`（不加 `-v`，数据保留）。

## 4. 启动后端

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

首次连接 Postgres 时会自动执行 Alembic 迁移。

访问 http://localhost:8000/docs 查看 Swagger API。

## 5. 启动前端（开发模式）

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 http://localhost:5173 。Vite 会将 `/api` 代理到后端 `8000` 端口。

**前端功能**：会话侧边栏（新建 / 列表 / 搜索 / 重命名 / 删除）、SSE 流式输出、Markdown 渲染、多行输入（Shift+Enter 换行）、字数限制、停止生成、深色模式、**看图作诗**（上传图片触发创作）。

## 看图作诗

在聊天输入框点击「图片」上传 JPEG / PNG / WebP（最大 4MB），可仅传图或附加文字说明体裁与主题。

**流程**：视觉模型（默认 `qwen-vl-max`）理解画面意境 → 合成描述后走现有创作 Agent（`qwen-plus` + `writing_assistant`）→ 流式输出诗作。

| 配置项 | 说明 |
|--------|------|
| `VISION_MODEL` | 视觉模型，默认 `qwen-vl-max` |
| `OPENAI_API_KEY` | 与文本 LLM 共用 DashScope API Key |

- 仅上传图片、无文字时，默认创作 **五言绝句**
- 图片**不持久化**；会话历史中保存的是画面描述文字，刷新后不可回看原图
- 每次看图作诗会调用两次 LLM（视觉描述 + 诗词创作），请注意 API 用量

## 6. 生产构建（前后端一体）

```bash
cd frontend && npm run build && cd ..
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

构建后访问 http://localhost:8000 即为聊天界面，API 仍在 `/api/v1`。

## 7. Docker 全栈（App + Postgres + Redis）

```bash
docker compose -f docker-compose.dev.yml up --build
```

Compose 栈包含 **PostgreSQL + Redis + App**，启动时自动执行 `alembic upgrade head` 并完成数据库迁移。访问 http://localhost:8000（需先构建前端或挂载 dist）。

## 本地开发 vs 全栈 Docker

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
├── data/
│   ├── corpus/           # 诗词 Markdown 语料
│   ├── authors.json      # 作者库
│   └── chroma_db/        # 向量库（构建后生成）
├── docs/                 # 项目文档（本目录）
└── scripts/              # 建索引、评估、部署脚本
```

详见 [架构文档 · 目录与模块对应](architecture.md#8-目录与模块对应)。
