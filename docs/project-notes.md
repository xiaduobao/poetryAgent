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

---

## 2026-06-18 · 前端手机端适配

**问**：前端页面做一下适配，可以适合手机页面。

**答**：在已有移动端侧栏抽屉（`md:hidden` + 遮罩）基础上，补齐小屏体验：

- `index.html`：`viewport-fit=cover`、主题色 meta
- `index.css`：`100dvh`、横向溢出隐藏、iOS 安全区 `.safe-area-top/bottom`、Markdown 表格横向滚动
- `AppLayout`：顶栏/游客条紧凑；侧栏传 `onClose` 关闭按钮
- `SessionSidebar`：触控下会话菜单常显；宽度 `max-w-[85vw]`
- `ChatInput`：小屏仅图标按钮、字数统计紧凑、输入框 `text-base` 防 iOS 缩放
- `MessageList` / `MessageBubble` / `EmptyState` / `PromptChips` / `AuthPage` / `Dialog`：减小内边距与字号

**标签**：`other`

---

## 2026-06-18 · 输入框支持图片拖拽

**问**：输入框可以支持图片拖拽放入。

**答**：`ChatInput` 输入区域支持将 JPEG/PNG/WebP 图片拖入，校验规则与点击上传一致（格式、4MB 上限）。拖入时显示高亮与「松开以添加图片」提示；逻辑复用 `processImageFile`，与文件选择共用。

**标签**：`other`

---

## 2026-06-18 · 推荐词点击自动发送

**问**：点击推荐词自动发送。

**答**：空状态示例词与对话后跟进推荐词点击后直接调用 `handleSend` / `onSend`，不再仅填入输入框；流式输出中会忽略点击。

**标签**：`other`

---

## 2026-06-18 · LangSmith 403 Forbidden

**问**：日志 `langsmith.client` WARNING，`403 Forbidden` POST `runs/multipart`。

**答**：LangSmith 追踪上报失败，不影响对话/RAG。`.env` 里 `LANGSMITH_TRACING=true` 但 API Key 无效/过期时常见。最快：`LANGSMITH_TRACING=false` 重启；要用追踪则在 smith.langchain.com 重新生成 Key。见 `docs/deploy-troubleshooting.md` §12.1。

**标签**：`config`

---

## 2026-06-18 · 手机端：用户提问可见 + JSON 换行

**问**：提示词不见了；JSON 里 appreciation 太长要换行；手机适配差。

**答**：

1. **提问不见**：长回复滚到底，用户气泡被顶出视野 → 消息区顶部固定「你的提问」条；用户气泡加「你」标签
2. **JSON 横向滚动**：`.prose pre/code` 改 `pre-wrap` + `word-break`；助手气泡手机端全宽
3. **手机滚动**：消息列表改用原生 `overflow-y-auto`，iOS 触控更顺
4. **Prompt**：创作 JSON 的 `appreciation` 提示模型用 `\n` 分段

**标签**：`other`

---

## 2026-06-18 · 用户消息左对齐、去掉「你」标签

**问**：去掉气泡里的「你」字；我发的消息要和 AI 内容对齐。

**答**：`MessageBubble` 用户消息改为与助手回复同宽、左对齐，移除「你」标签，保留紫色背景区分角色。

**标签**：`other`

---

## 2026-06-18 · 用户消息右对齐、宽度随内容

**问**：用户气泡太丑，要右边对齐、不要铺满。

**答**：用户消息 `justify-end` + `w-fit max-w-[85%]`，按文字收缩；AI 回复仍左对齐全宽展示。

**标签**：`other`

---

## 2026-06-18 · 用户消息与 AI 内容右缘对齐

**问**：用户气泡右缘要与下方 AI 内容区右缘对齐（如图红线）。

**答**：用户与 AI 共用同一列宽（`max-w-3xl` 内容区全宽）；AI `w-full`，用户外层 `flex justify-end` + 内层 `w-fit`，右缘对齐、宽度随文字。

**标签**：`other`

---

## 2026-06-18 · MessageBubble 解析错误修复

**问**：Vite 报 `[PARSE_ERROR] Unexpected token` 于 `MessageBubble.tsx:90`。

**答**：气泡内容 `<div>`（圆角背景层）缺少闭合 `</div>`，导致 JSX 结构不完整。补全后即可正常编译。

**标签**：`other`

---

## 2026-06-18 · 助手回复排版优化（JSON 卡片化）

**问**：助手文字输出排版差，末尾 JSON 代码块不美观，需要更好格式。

**答**：
1. 前端 `parseStructuredOutput.ts` 解析末尾 ` ```json ` 块，正文继续 Markdown 渲染
2. 新增 `PoemCard` 组件：诗题、作者/朝代/体裁、主旨、名句（引用样式）、鉴赏要点分段展示
3. 流式输出时用 `stripStreamingJsonBlock` 隐藏未完成的 JSON
4. `prompts.py` 要求模型正文用 `###` 标题、列表、引用块分段，JSON 仅作结构化补充
5. `index.css` 增强 prose 的 h3、列表、blockquote 样式

**标签**：`other`

---

## 2026-06-18 · 意图识别完整重构（复合问题）

**问**：用户单条消息可能含多个问题，现有意图识别只能选一个路径，如何优化？

**答**：
1. **规则引擎**：`app/agent/intent_rules.py` 按 priority 匹配；`strip_user_input()` 去 `<user_input>` 包裹后再分类
2. **结构化分类**：`app/agent/intent_classifier.py` 输出 JSON（intent + confidence），替代子串解析
3. **复合流水线**（`COMPOUND_INTENT_ENABLED=true`）：`decompose_query` → 并行 `execute_subtask` → `compound_synthesis` 流式合成
4. **评测**：`tests/eval/intent_golden_set.json` + `python -m app.eval.intent_eval --report`
5. **前端**：复合问题展示多个 intent badge；SSE 新增 `decomposing` / `executing` / `subtasks` 事件

**标签**：`other`

---

## 2026-06-18 · 诗词摘要卡片 UI 美化

**问**：聊天里「诗词摘要」结构化卡片样式太丑（多层边框、系统字体、表单感强）。

**答**：
1. 重写 `frontend/src/components/chat/PoemCard.tsx`：去掉「诗词摘要」顶栏与内层嵌套边框，改为左侧渐变竖线 + 宣纸渐变背景的卷轴式卡片。
2. 诗题、正文、名句改用 **Noto Serif SC** 衬线体（`index.html` 引入 Google Font），增大字距、居中排诗。
3. 作者/朝代/体裁/主旨改为圆角 chip，名句用「」书名号样式；样式集中在 `frontend/src/index.css` 的 `.poem-card*` 类。

**标签**：`other`

---

## 2026-06-18 · 首页添加 GitHub 项目链接

**问**：在首页添加链接到 GitHub 项目 README（https://github.com/xiaduobao/poetryAgent）。

**答**：
1. 新增 `frontend/src/lib/siteLinks.ts` 常量 `GITHUB_REPO_URL`。
2. 空状态页 `EmptyState.tsx` 底部增加「查看 GitHub 项目 README」文字链接。
3. 顶栏 `AppLayout.tsx` 增加 GitHub 图标按钮，任意页面均可跳转。

**标签**：`other`

---

## 2026-06-18 · GitHub 链接改为常驻入口

**问**：GitHub 链接不能只在空状态页显示，开始对话后就消失，需要时刻可访问。

**答**：
1. 抽取 `GithubRepoLink` 组件（`frontend/src/components/GithubRepoLink.tsx`）。
2. **顶栏**始终显示「GitHub」文字链接；**输入框下方**常驻「GitHub 项目 README」；**侧边栏底部**（桌面端）同样常驻。
3. 移除 `EmptyState` 中仅空态可见的链接，避免对话开始后消失。

**标签**：`other`

---

## 2026-06-18 · 创作诗词正文与卡片衔接优化

**问**：创作诗词时，上方说明文字与下方卡片内容重复、视觉突兀。

**答**：
1. `parseStructuredOutput.ts` 新增 `stripDuplicatedPoemFromMarkdown`：JSON 含 `lines` 时自动去掉正文中重复的诗句/诗题。
2. `PoemCard` 改为消息气泡内的分隔区块（顶部分割线 + 衬线排诗），去掉独立宣纸色卡片与左侧色条。
3. `MessageBubble` 将 prose 与 `PoemCard` 分块渲染，避免 prose 样式污染卡片。
4. `prompts.py` 创作提示改为：正文只写创作说明，诗句仅放 JSON `lines`。

**标签**：`other`

---

## 2026-06-18 · 配图示例点击需先上传图片（方案 A）

**问**：点击「上传风景照，写一首五言绝句」会直接发纯文字，未要求选图。

**答**：
1. `promptExamples.ts` 示例改为 `PromptExample` 类型（`text` / `image`）。
2. 点击 `image` 类型：填入输入框、弹出文件选择器、显示提示，**不自动发送**；未选图时发送按钮禁用。
3. `ChatInput` 暴露 `openImagePicker()`；`PromptChips` 配图示例显示 📷 图标。

**标签**：`other`
