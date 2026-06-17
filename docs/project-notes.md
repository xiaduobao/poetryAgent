# 项目问答笔记

由 Agent 根据对话自动整理，记录开发过程中的问题与结论。

格式：日期 · 标题 → 问 / 答 / 标签

---

## 2026-06-17 · 自动文档 Skill 说明

**问**：希望以后问任何问题，Agent 都能自动整理保存到项目文档，而不是手动要求记录。

**答**：
- 已配置 Skill：`.cursor/skills/poetry-deploy-journal/SKILL.md`
- 部署类 → `docs/deploy-troubleshooting.md`
- 其他类 → 本文件 `docs/project-notes.md`
- 每次回答后自动追加，无需说「记录一下」

**标签**：`config`

---

## 2026-06-17 · 新镜像构建好后发布到 ECS

**问**：ACR 新 image 构建好了，发布指令是什么？

**答**：在项目根目录执行（本地 Mac）：

```bash
# 日常最常用：只拉最新镜像并重启（推荐）
./scripts/deploy/deploy.sh --pull

# 同时更新了 compose 脚本 / docker-compose 配置
./scripts/deploy/deploy.sh

# 只改了 .env.prod
./scripts/deploy/deploy.sh --env-only

# 首次或需同步模型/向量库
./scripts/deploy/deploy.sh --with-data
```

前提：`scripts/deploy/deploy.env` 已配置 `ECS_HOST`、`POETRY_AGENT_IMAGE`；ECS 已 `docker login` 个人 ACR（或在 deploy.env 配 `ACR_USERNAME`/`ACR_PASSWORD`）。

验证：`http://8.134.168.40/` 或 SSH 后 `./scripts/deploy/remote-compose.sh health`

**标签**：`deploy`

---

## 2026-06-17 · 容器内找不到 Embedding 模型路径

**问**：`FileNotFoundError: Path ./data/models/BAAI--bge-small-zh-v1.5 not found`

**答**：`.env.prod` 必须填 **`ls data/models/` 里真实存在的目录名**。

| 来源 | 典型目录名 |
|------|------------|
| `download_models.py` | `BAAI--bge-small-zh-v1.5`（repo 的 `/` 换成 `--`） |
| 手动 / 旧环境（你的 ECS） | `bge-small-zh-v1.5`（无 BAAI 前缀） |

**你的 ECS 现状**：只有 `bge-small-zh-v1.5`，还需同步 rerank 模型。

```env
EMBEDDING_MODEL=./data/models/bge-small-zh-v1.5
RERANK_MODEL=./data/models/bge-reranker-base
```

```bash
python scripts/download_models.py
./scripts/deploy/deploy.sh --with-data
./scripts/deploy/deploy.sh --env-only
```

**标签**：`deploy` `data` `rag`

---

## 2026-06-17 · deploy.sh --env-only 会不会重建容器

**问**：`--env-only` 仅更新 `.env.prod` 并重启，不重建容器会不会有问题？

**答**：会。`docker compose restart` **不会**重新读取 `.env.prod`**，容器内仍是旧环境变量。应使用 `up -d --force-recreate` 重建容器（不 pull、不 build）。

| 命令 | 拉新镜像 | 读新 .env.prod | 场景 |
|------|----------|----------------|------|
| `--pull` | ✅ | ❌（除非一并 recreate） | 新镜像 |
| `--env-only` | ❌ | ✅（recreate） | 只改配置 |
| `restart` | ❌ | ❌ | 进程挂了快速拉起 |

已修复：`--env-only` 改为调用 `remote-compose.sh recreate`。

**补充（2026-06-17）**：旧版 `--env-only` 有两个坑：
1. 远端若未同步新脚本，仍执行 `restart` 而非 `recreate`
2. `restart` 本身不读新 `.env.prod`

现版 `--env-only` 会：同步 compose + deploy 脚本 → 上传 `.env.prod` → `force-recreate` → 打印容器创建时间与 `EMBEDDING_MODEL` 校验。

**标签**：`deploy`

---

## 2026-06-17 · ECS 上 Docker Compose 启动命令

**问**：ECS 上 docker compose 启动命令？

**答**（SSH 登录后 `cd /opt/poetry-agent`）：

```bash
# 推荐
./scripts/deploy/remote-compose.sh pull-up   # 拉 ACR 镜像 + 启动
./scripts/deploy/remote-compose.sh recreate  # 重建 app（加载新 .env.prod）
./scripts/deploy/remote-compose.sh ps|logs|health

# 原生
source .compose.env   # 含 POETRY_AGENT_IMAGE=...
docker compose -f docker-compose.prod.yml pull poetry-agent
docker compose -f docker-compose.prod.yml up -d --no-build
```

本地发布：`./scripts/deploy/deploy.sh --pull`

**标签**：`deploy`

---

## 2026-06-17 · 本地开发改用 Docker Postgres + Redis

**问**：将项目本地也用 postgres 和 redis，用 docker 构建。

**答**：
- 新增 `docker-compose.infra.yml`：仅 Postgres 16 + Redis 7，端口映射到 `localhost:5432` / `6379`
- `.env.example` / `.env` 默认配置 `DATABASE_URL`、`REDIS_URL`、`RATE_LIMIT_STORAGE_URI` 指向 localhost
- 应用在宿主机跑 `uvicorn --reload`，与生产栈行为一致（迁移、Checkpoint、Redis 限流）
- 全栈仍可用 `docker compose -f docker-compose.dev.yml up --build`

```bash
docker compose -f docker-compose.infra.yml up -d
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**标签**：`docker` `config`

---

## 2026-06-17 · SSE 流式 chat 报 connection is closed

**问**：`/chat/stream` 结束时报错 `asyncpg InterfaceError: connection is closed`，保存 assistant 消息失败。

**答**：根因是 FastAPI 的 `Depends(get_db)` 在 SSE 整段流式期间一直占着连接；LLM 生成几十秒后 Postgres 回收空闲连接，结束时 `add_message` / `commit` 就会失败。

修复：
1. `/chat/stream` 不再注入 `get_db`，会话校验/创建与写消息均用 `get_session_factory()` 短连接
2. `get_current_user`、`require_chat_quota` 改为独立短连接，避免认证阶段占用请求级 session
3. PostgreSQL 连接池增加 `pool_pre_ping=True`、`pool_recycle=1800`

重启 uvicorn 后重试流式对话即可。

**标签**：`config` `other`

---

## 2026-06-17 · 混合检索 LangSmith 耗时 76s

**问**：LangSmith trace 里 `hybrid_retrieve` 约 76s，`VectorStoreRetriever` 仅 0.88s，为何这么慢？

**答**：向量检索 + BM25 都很快（语料约 202 篇，BM25 内存打分毫秒级）。剩余 ~75s 几乎全在 **BGE Rerank**（`app/rag/retriever.py` 的 `_rerank` → `FlagReranker.compute_score`），该步骤未单独打 span，所以 trace 里只看到 `VectorStoreRetriever` 子节点。

典型原因：
1. **CPU 推理**：`use_fp16=False`，ECS 无 GPU 时，对合并后的 8～16 条长文档（单条可达 ~1500 字）逐对打分，单请求 30～80s 常见
2. **冷启动**：若 lifespan warmup 失败，首次请求还会在 `hybrid_retrieve` 内加载 rerank 权重

优化方向：启动日志确认 `Hybrid retriever ready`；减小 `RETRIEVAL_TOP_K`；rerank 前截断 `page_content`（如 512 字）；有 GPU 时 `use_fp16=True`；或换更小 rerank 模型 / 按需关闭 rerank。

**标签**：`rag` `config`

---

## 2026-06-17 · 查看混合检索各步骤耗时

**问**：有什么办法可以看到主要耗时在哪？

**答**：已在 `app/rag/retriever.py` 加三层观测：

1. **LangSmith 子 Span**（需 `LANGSMITH_TRACING=true`）：`hybrid_retrieve` 下可展开 `VectorStoreRetriever`、`bm25_search`、`bge_rerank`；冷启动时还有 `load_reranker`
2. **Run metadata `step_timings_ms`**：在 LangSmith 该 run 的 Metadata 里看 `vector` / `bm25` / `merge` / `rerank` 毫秒数
3. **应用日志**：总耗时 ≥1s 时打 `hybrid_retrieve slow: {...}`

本地快速看日志：`LANGSMITH_TRACING=false uvicorn app.main:app --reload`，发一条 RAG/chat 请求后 `grep hybrid_retrieve` 日志。

**标签**：`rag` `config`

---

## 2026-06-17 · Rerank 96s 优化

**问**：`hybrid_retrieve slow` 里 rerank 约 96s，有什么优化办法？

**答**：根因是 CPU 上对合并候选的**全文**（单条可达 ~1500 字）做 cross-encoder。已在代码里默认启用：

1. **截断**：`RERANK_MAX_LENGTH=512`，只取标题+正文前缀送入 rerank
2. **限候选**：`RERANK_MAX_CANDIDATES=6`（合并后最多 6 条进 rerank）
3. **批大小**：`RERANK_BATCH_SIZE=16`
4. **可关闭**：`RERANK_ENABLED=false` 时直接用向量+BM25 顺序（延迟最低）

仍慢可换 `bge-reranker-v2-m3` 或 ECS 加 GPU；向量 ~3s 是 CPU embedding 查询，与 rerank 独立。

**标签**：`rag` `config`

---

## 2026-06-17 · 启动时本地加载 RAG 模型（失败即退出）

**问**：将 model 加载放在启动时；加载失败直接报错；打印路径便于排查；不要远端请求；`.env` 模型路径用相对路径。

**答**：

1. 启动顺序（`app/main.py` lifespan）：先 `warmup_rag_models()` 加载 embedding / rerank，再建向量库、预热 retriever；任一步失败则进程退出。
2. `resolve_model_path()` 只认本地目录：`.env` 填 `./data/models/...`，解析为 `ROOT_DIR` 下绝对路径；目录不存在则 `FileNotFoundError`，日志含 `env=` 与 `resolved=`。
3. 禁止 HuggingFace 远端：设置 `HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1`，embedding 使用 `local_files_only=True`。
4. 配置示例：

```bash
EMBEDDING_MODEL=./data/models/BAAI--bge-small-zh-v1.5
RERANK_MODEL=./data/models/BAAI--bge-reranker-base
```

缺模型时先 `python scripts/download_models.py`，再启动服务。

**标签**：`rag` `config`

---

## 2026-06-17 · download_models 识别 .env 本地路径

**问**：`.env` 填 `./data/models/BAAI--bge-reranker-base` 时，`download_models.py` 把路径当 repo id 下载失败。

**答**：脚本已区分「本地相对路径」与 `BAAI/bge-reranker-base` 这类 HF ID。本地路径目录不存在时，从目录名推断 repo（如 `BAAI--bge-reranker-base` → `BAAI/bge-reranker-base`）并下载到该路径。重新执行：

```bash
python scripts/download_models.py
```

**标签**：`rag` `config`
