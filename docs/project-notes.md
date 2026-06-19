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

## 2026-06-18 · 「推荐作者主要作品」意图识别修复

**问**：「推荐王加宝的主要作品」被识别为作者查询后，输出冗长传记 + 诗词卡片，体验不对。

**答**：
1. **规则**：新增 `author_works` 规则（`推荐/有哪些` + `作品/代表作/名篇` → `tool_author`），「推荐王加宝的主要作品」规则命中，不再依赖 LLM 误判。
2. **输出**：`tool_author` 等工具类意图不再附加诗词 JSON 卡片提示；整理回答时要求以列表呈现代表作。
3. **测试**：`tests/unit/test_intent.py` 与 golden set 增加该用例。

**标签**：`other`

---

## 2026-06-18 · 配图示例点击需先上传图片（方案 A）

**问**：点击「上传风景照，写一首五言绝句」会直接发纯文字，未要求选图。

**答**：
1. `promptExamples.ts` 示例改为 `PromptExample` 类型（`text` / `image`）。
2. 点击 `image` 类型：填入输入框、弹出文件选择器、显示提示，**不自动发送**；未选图时发送按钮禁用。
3. `ChatInput` 暴露 `openImagePicker()`；`PromptChips` 配图示例显示 📷 图标。

**标签**：`other`

---

## 2026-06-18 · 简历描述与项目优化建议

**问**：如何将 poetryAgent 写进简历？还需要优化哪些内容？

**答**：

**简历一句话**：古典诗词鉴赏智能助手 — 基于 LangGraph 的多分支 Agent + 混合检索 RAG，全栈上线（React / FastAPI / PostgreSQL / Redis），部署于阿里云 ECS。

**可量化素材**：语料约 200 首诗词 Markdown；7+ 工具（格律/作者/对比/主题/创作等）；混合检索 BM25+向量+BGE-Rerank；意图 golden set + RAG golden set；CI pytest 覆盖率 ≥40%。

**优先优化（简历前）**：
1. README 顶部加 Demo 链接（`cnpoetry.top` 或 GitHub Pages 截图）+ CI badge
2. 跑 `eval_rag.py` / `intent_eval` 记下命中率、延迟 p50，写进 README「效果指标」
3. 准备 1 张架构图 + 2～3 张产品截图（流式对话、引用来源、LangSmith Run 树）
4. 面试故事：复合问题拆解并行、规则+LLM 意图、Checkpoint 降级链、ACR 部署

**标签**：`other`

---

## 2026-06-18 · 作为简历项目是否合格

**问**：这个项目作为个人简历项目合格不？

**答**：**合格，且偏强**（AI 应用 / 后端 / 全栈初级～中级）。覆盖 RAG+Agent+全栈+上线+可观测+评测，超过多数「只调 API 的 Demo」。短板：缺量化效果数据、评测集偏小、无真实用户指标；投大厂需把 compound/混合检索/部署坑讲深。校招/1～3 年可作主项目；3 年+建议搭配业务侧项目。

**标签**：`other`

---

## 2026-06-18 · 十年后端、首个完整 AI 项目如何写简历

**问**：工作十年、以前做后端，这是第一个完整 AI 项目，怎么定位？

**答**：
- **项目本身合格**，但对 10 年资历是「AI 能力证明」，不是「职级证明」；简历主线仍应是十年后端（高并发/分布式/业务），AI 项目作**转型亮点**（1 个项目块，约占项目经历 20～30%）。
- **叙事**：「用工程化方式落地 LLM 应用」— 强调部署、可观测、降级、评测、配额，而非只会调 Prompt。
- **面试准备**：混合检索取舍、compound 并行、Checkpoint 降级、JWT+限流；对比「若在生产会怎么做」（缓存、异步队列、成本管控）。
- **缺口**：缺业务规模与线上 AI 指标；可补 1 个与工作相关的 AI 试点或开源贡献，避免被当成「兴趣 Demo」。

**标签**：`other`

---

## 2026-06-18 · 局部有限 ReAct（工具多轮 / 低置信度兜底 / RAG-as-tool）

**问**：局部引入有限 ReAct。

**答**：
- 新模块 `app/agent/react_loop.py`：`run_limited_react`、`poetry_search` 工具（混合检索封装）
- **工具多轮**：`tool_*` 意图走 ReAct 循环（默认 max 3 步），如 lookup → meter
- **低置信度兜底**：LLM 意图且 confidence < 0.65 时走 ReAct（规则命中仍走快路径）
- **RAG 快路径保留**：高置信 `rag` 仍直接 `retrieve_rag`，不绕 ReAct
- 配置见 `.env.example`：`REACT_*` 系列；测试 `tests/unit/test_react_loop.py`

**标签**：`other`

---

## 2026-06-19 · 「分析这首诗的格律」未继承上文诗题

**问**：用户先查《枫桥夜泊》原文，再点「分析这首诗的格律」，助手回复未提供诗题/原文。

**答**：
- **根因**：`tool_meter` 提示只要求「从当前输入提取诗题」，指代问法（这首诗/上面那首）未解析对话历史。
- **修复**：新增 `app/agent/context_resolver.py`，从历史上文（《》书名号、工具 JSON 返回、助手回答）解析诗题/作者/原文，并注入 ReAct / 工具调用 / 总结阶段。
- **涉及文件**：`react_loop.py`、`graph.py`、`compound_pipeline.py`、`prompts.py`；测试 `tests/unit/test_context_resolver.py`。

**标签**：`other`

---

## 2026-06-19 · 手机端侧边栏透明叠层

**问**：手机版打开会话列表时「新建对话」区域透明，背后聊天内容透出来，体验差。

**答**：
- **根因**：`SessionSidebar` 使用 `bg-muted/30`（30% 不透明），桌面并排尚可，移动端抽屉叠层会透出主界面。
- **修复**：移动端（有 `onClose` 时）改为 `bg-background` 实底；抽屉改为左栏 + 右侧半透明遮罩的 flex 布局。
- **文件**：`frontend/src/components/sidebar/SessionSidebar.tsx`、`frontend/src/components/layout/AppLayout.tsx`。

**标签**：`other`

---

## 2026-06-19 · 意图识别路由日志

**问**：意图识别需要更多日志，便于知道走了哪条链路。

**答**：
- 新增 `app/agent/route_log.py`，统一 `[agent-route]` 前缀。
- 关键节点：`intent_classify`（rule/llm/suggested + rule 名）、`decompose`、`sub_intents`、`prepare_start`、`execution_path`（rag/tool/react/chat）、`tool_path`、`react_start/done`、`compound_route`。
- 排查：`grep '[agent-route]'` 或按 `thread_id` 过滤容器日志。

**标签**：`other`

---

## 2026-06-19 · 工具路径不再无条件走 ReAct

**问**：无论如何都跳转到 react_loop，因为 confidence 写死为 1.0，阈值判断失效。

**答**：
- **根因**：`react_tool_loop_enabled=true` 时所有 `tool_*` 强制 ReAct，与 confidence 无关；规则 confidence 默认全是 1.0。
- **修复**：新增 `should_use_react_tool_loop()`——`confidence >= 0.65` 走 `legacy_single`，低于阈值或指代性提问（缺诗题）才 ReAct；各规则设差异化 confidence（lookup 0.95、poem_title 0.75 等）。
- **日志**：`tool_path` 现含 `source`、`confidence`、`path=legacy_single|react_loop`。

**标签**：`other`

---

## 2026-06-19 · 多意图时 rule_based_intent 怎么处理

**问**：`intent_rules.rule_based_intent` 若用户一句话含多个意图怎么办？

**答**：
- `match_intent_rules` 会返回**全部命中规则**（按 priority 排序）；`rule_based_intent` / `classify_single_intent` **只取第一条**，其余丢弃。
- 主链路走 `classify_single_intent`，`rule_based_intent` 主要用于 eval。
- **复合问题**需开 `COMPOUND_INTENT_ENABLED=true`：`decompose_query` 按「并/还有/另外…」拆句，子句分别分类；仅当子意图**互不相同**才并行 compound，否则仍单路径。
- 无连接词的叠意图（如同时像 lookup + meter）目前**无法**在规则层并行，只能靠 priority 决胜负。

**标签**：`other`

---

## 2026-06-19 · 规则层显式 multi-intent（已撤销）

**说明**：曾新增 `classify_intent_rules` / `RULE_MULTI_INTENT_ENABLED` 支持无连接词多意图并行；已回退。多意图仍仅通过 `COMPOUND_INTENT_ENABLED` + 连接词拆解；规则层恢复为 `match_intent_rules` 取最高 priority 单意图。

**标签**：`other`

---

## 2026-06-19 · 意图识别链路梳理

**问**：当前意图识别链路逻辑清晰梳理。

**答**：见下方用户回复中的总览图与分层说明；日志统一 grep `[agent-route]`。

**标签**：`other`

---

## 2026-06-19 · 意图识别档 A 优化（上下文 + 融合 + 规则冲突）

**问**：执行档 A 优化意图识别。

**答**：
1. **分类前上下文增强**：`prepare_query_for_intent()` 在 `classify_single_intent` 入口调用 `resolve_poem_context` + `augment_query_with_context`；`graph.classify_intent` 与 compound 路径传入 `messages`。
2. **规则/suggested 融合**：rule 与 decompose 的 `suggested_intent` 一致 → `rule+suggested` 取较高 confidence；冲突 → 降 confidence 或 suggested≥0.9 覆盖弱 rule；suggested 下限 0.7（原 0.8）以减少重复 LLM。
3. **规则冲突检测**：`resolve_rule_match()` / `is_ambiguous_rule_match()` — 不同 intent 且 priority 差≤10 时 confidence 压至 ≤0.58，触发 ReAct。
4. **规则负向条件**：`theme` 排除「作品/代表作」；`poem_title` 排除「格律/平仄/押韵」。
**标签**：`other`

---

## 2026-06-19 · 意图识别链路梳理（当前实现）

**问**：梳理当前意图识别的链路逻辑。

**答**：入口由 `COMPOUND_INTENT_ENABLED` 分叉 → 单路径 `classify_intent` 或复合 `decompose→classify_sub_queries`；核心分类均为 `classify_single_intent`（上下文增强 → 规则 → rule/suggested 融合 → LLM）；路由 `rag|tools|chat`；执行层 ReAct 兜底低置信/指代。日志：`grep '[agent-route]'`。

**标签**：`other`

---

## 2026-06-19 · 修复前端 CI ESLint 错误

**问**：修复 CI「Install and lint」步骤的 ESLint 报错。

**答**：
1. `button.tsx`：移除 `buttonVariants` 导出（仅组件文件导出组件）。
2. `input.tsx` / `textarea.tsx`：空 interface 改为 `type` 别名。
3. `AuthContext.tsx`：初始用户加载改为 effect 内 `.then()` 异步链，避免 effect 中同步 `setState`；`useAuth` 移至 `hooks/useAuth.ts`；Context 定义拆至 `contexts/auth-context.ts`。
4. `useSessions.ts`：合并初始加载与 debounce 为一个 effect，首次 `setTimeout(..., 0)` 避免 effect 内同步 `setState`。

验证：`cd frontend && npm run lint`

**标签**：`other`

---

## 2026-06-19 · 修复后端 CI Ruff import 排序

**问**：backend job「Ruff lint」失败，`app/agent/graph.py` I001 import 块未排序。

**答**：`from app.agent.checkpoint import get_checkpointer` 误插在第三方 `langgraph` import 之间；移至本地 `app.*` import 块（`compound_pipeline` 之前）。验证：`ruff check app/agent/graph.py` 或 `ruff check --fix app/agent/graph.py`。

**标签**：`other`

---

## 2026-06-19 · 修复全部 backend Ruff CI 错误

**问**：`ruff check app tests` 需全部通过。

**答**：`ruff check --fix app tests` 自动修复 12 项（未使用 import、import 排序）；手动改 `app/tools/meter.py` 列表推导变量 `l` → `line`（E741）。验证：`ruff check app tests`。

**标签**：`other`

---

## 2026-06-19 · Pre-commit 接入 CI lint

**问**：将 `ruff check app tests` 与 `cd frontend && npm run lint` 放入 pre-commit 验证。

**答**：新增 `.pre-commit-config.yaml`（local hooks）；`requirements.txt` 增加 `pre-commit`。安装：`pip install pre-commit && pre-commit install`；全量：`pre-commit run --all-files`。

**标签**：`other`

---

## 2026-06-19 · 修复 CI Pytest ModuleNotFoundError

**问**：CI Pytest 失败，`tests/conftest.py` 报 `ModuleNotFoundError: No module named 'app'`。

**答**：`pyproject.toml` 的 `[tool.pytest.ini_options]` 增加 `pythonpath = ["."]`，让 pytest 从项目根目录解析 `app` 包（与本地 `uvicorn`/开发一致）。验证：`pytest tests/ -v --cov=app --cov-fail-under=40`。

**标签**：`other`

---

## 2026-06-19 · 简历呈现建议与待优化项

**问**：项目写进简历的建议，以及当前还有哪些点需要优化。

**答**：
- **简历写法**：项目名 + 一句话定位（古典诗词 RAG + LangGraph Agent 全栈）；3～5 条 STAR  bullet，突出混合检索、意图路由、SSE 流式、JWT 配额、ECS 部署；技术栈按 JD 裁剪（AI 岗强调 RAG/Agent，后端岗强调 FastAPI/Postgres/CI）。
- **面试可讲**：分块策略、混合检索+Rerank、规则+LLM 意图融合+ReAct 兜底、复合问题并行子任务、LangSmith 可观测、看图作诗多模态链路。
- **高优先级优化**：① README 顶部加在线 Demo 链接 + 架构/GIF；② 跑 Ragas 并把指标写入 README（golden set 仅 3 条需扩到 20+）；③ 覆盖率从 40% 提到 60%+，补 Agent graph 集成测；④ CI 加 `eval_rag.py` 离线检索 smoke；⑤ 前端补 Vitest 或 Playwright。
- **中优先级**：HTTPS 域名、CI/coverage badge、docs/case-study.md 一页案例、量化 TTFT/规则命中率。

**标签**：`other`

---

## 2026-06-19 · Golden set 扩至 30 条并写入 RAG 评估指标

**问**：执行 Day 3-4：golden set 扩到 30 条，跑 eval，把指标写进 README。

**答**：
1. `tests/eval/rag_golden_set.json` 扩至 **30 条**（单篇赏析 20 + 主题/体裁 10）。
2. 运行 `python scripts/eval_rag.py`：**30/30 通过**，平均召回 **3.33 篇/查询**（202 篇语料向量库）。
3. `scripts/eval_rag.py` 新增 `--output reports/rag_eval.json`；README §9 增加「当前评估结果」表格。
4. 全链路 Ragas 需 API Key：`python scripts/eval_rag_ragas.py --output reports/ragas.json`

**标签**：`rag`

---

## 2026-06-19 · README 重构：Demo 链接 + 文档体系

**问**：Day 1-2：ECS Demo 链接、架构图、演示素材写入 README；将 README 内容抽取到 docs 并给出用户指引。

**答**：
1. README 顶部加入 **[cnpoetry.top](https://cnpoetry.top/)** Demo 徽章、演示视频/截图（`docs/materials/`）。
2. 架构简图 + 链接 `docs/architecture.md`；RAG 截图 `materials/Rag.png`。
3. 详细内容拆至 docs：`README.md`（文档首页）、`getting-started.md`、`deployment.md`、`testing-and-evaluation.md`、`observability.md`、`api-examples.md`、`corpus-management.md`。
4. 根 README 精简为入口 + 文档导航 + 快速开始命令。

**标签**：`other`

---

## 2026-06-19 · README 定位优化：弱化「学习项目」表述

**问**：曾建议不要强调学习项目，优化 README 定位。

**答**：副标题改为「已上线运行的 RAG + LangGraph Agent 全栈应用」；Badge Demo→Live；项目简介强调生产部署与 202 篇语料；许可证去掉「学习用途」；docs 中「在线 Demo」统一为「线上站点」。

**标签**：`other`

---

## 2026-06-19 · README 演示视频无法在首页内嵌播放

**问**：演示视频在 README 首页展示不出来怎么办？

**答**：
1. **根因（与体积无关）**：GitHub README 的 `<video>` **不支持**仓库内相对路径或 `raw.githubusercontent.com`；只认 `user-attachments`、`user-images.githubusercontent.com` 或 `releases/download/...` 等绝对 URL。当前 `docs/materials/poetryAgentDemo.mp4` 约 **3.2MB**，远低于 10MB 上限，**无需压缩**。
2. **当前方案（封面 + 点击播放）**：`[![...](docs/materials/poster.png)](.../blob/main/docs/materials/poetryAgentDemo.mp4)`，首页显示 poster，点击用 GitHub 内置播放器播放。
3. **若要在 README 内嵌播放器**：GitHub 网页打开 README 编辑 → 把 `poetryAgentDemo.mp4` **拖进编辑器** → 复制生成的 `user-attachments` URL → 写入 `<video src="https://github.com/user-attachments/assets/xxx" controls width="100%" playsinline poster="docs/materials/poster.png"></video>`。
4. **备选**：GitHub Release 挂 mp4 + `releases/download/...` URL。

**标签**：`other`

---

## 2026-06-19 · Ragas 评估报告（Context Recall 0.68）

**问**：添加 Ragas 报告。

**答**：30 条 golden set + `--retrieval-only --llm-model qwen-turbo` → `reports/ragas.json`，**context_recall = 0.6782**。修复 `result_to_dict` 处理失败用例；脚本新增 `--limit`、`--llm-model`。qwen-plus 免费额度耗尽时需换 turbo。

复现：`python scripts/eval_rag_ragas.py --retrieval-only --llm-model qwen-turbo --output reports/ragas.json`

**标签**：`rag`

---

## 2026-06-19 · 不同工具能否用不同 RAG 数量加速

**问**：不同的工具调用查询 RAG 是不是可以设不同数量，让返回更快？

**答**：**返回条数可以不同，但当前实现不会因此更快**。`allusion` 取 `[:3]`、`theme` 取 `[:6]`、`/api/v1/rag` 用 `top_k`（默认 4）、`poetry_search` 走完整 `retrieve()`（最终 `rerank_top_n=4`）——这些差异只影响**最终给 LLM 的文档数**，底层每次都跑同一套：向量 k=8 + BM25 k=8 + Rerank 最多 6 条候选。

要真正加速，需让 `HybridRetriever.retrieve()` 支持按场景传入 `retrieval_k` / `rerank_n` / `skip_rerank`（轻量工具如典故可 k=4、rerank_n=2 或跳过 rerank；鉴赏类保持 k=8、rerank_n=4）。多数工具（`author_query`、`poem_lookup`、`meter_analysis` 等）不走 RAG，只用 JSON 语料。

**标签**：`rag`

---

## 2026-06-19 · 修复 pytest 单元测试失败

**问**：fix the unitest error

**标签**：`other`

---

## 2026-06-19 · 可观测性文档展示 LangSmith 截图

**问**：在可观测性文档中展示 `langsmith.png` 与 `Rag.png`

**标签**：`other`

---

## 2026-06-19 · README 演示视频内嵌播放

**问**：让演示视频在 README 中直接渲染出来

**标签**：`other`

---

## 2026-06-19 · README 架构图替换为 Mermaid

**问**：架构节的 Rag.png 不对，去掉并画最新的

**标签**：`other`

---

## 2026-06-19 · README 去掉技术亮点章节

**问**：技术亮点去掉吧

**答**：`README.md` 删除「技术亮点」表格及 `interview-highlights.md` 引导语；该文档仍保留在「文档导航」中。

**标签**：`other`

---

## 2026-06-19 · 页面慢因 Google Fonts 外链

**问**：浏览器访问 cnpoetry.top 很慢，为什么会请求 `fonts.googleapis.com`？

**标签**：`config`

---

## 2026-06-19 · 移除 Google Fonts 外链

**问**：采用最快方案，删掉 Google Fonts，用系统回退字体。

**答**：删除 `frontend/index.html` 中 `fonts.googleapis.com` / `fonts.gstatic.com` 三行 `<link>`。诗卡仍用 `font-family: "Noto Serif SC", "Songti SC", "STSong", serif`，无外链时自动落到宋体。国内首屏不再请求 Google CDN。

**标签**：`config`

---

## 2026-06-19 · README「功能演示」区块空白

**问**：GitHub README 的「功能演示」没有内容，只显示空白/破损图标。

**答**：
1. **根因**：GitHub README 的 `<video>` 不支持仓库内相对路径（`docs/materials/poetryAgentDemo.mp4`），只认 `user-attachments`、`user-images.githubusercontent.com` 或 `releases/download` 等绝对 URL。
2. **修复**：改为封面图 + 链接——`[![...](docs/materials/poster.png)](https://github.com/xiaduobao/poetryAgent/blob/main/docs/materials/poetryAgentDemo.mp4)`，首页可见 poster，点击跳转播放。
3. **若需内嵌播放器**：当前 mp4 约 3.2MB，直接在 GitHub README 编辑器拖拽上传，用返回的 `user-attachments` URL 写 `<video src="..." controls>` 即可（无需压缩）。
**标签**：`other`

---

## 2026-06-19 · qwen3.7-plus 比 qwen-plus 慢很多

**问**：从 `qwen-plus` 换到 `qwen3.7-plus` 后接口慢很多（LangSmith 显示 `stream_final_answer` ~55s）。

**答**：
1. **根因**：`qwen3.7-plus` 是**混合思考模型，默认开启思考模式**（`enable_thinking=true`）。Agent 一次请求会多次调 LLM（`decompose_query` ~8s + `prepare_tool_call` ~3s + `stream_final_answer` ~55s），每轮都先「深度推理」再输出，体感比 `qwen-plus` 慢数倍。
2. **修复**：`.env` / `.env.prod` 设 `LLM_ENABLE_THINKING=false`；代码 `get_llm()` 对 `qwen3*` 模型经 `extra_body` 传 `enable_thinking: false`。
3. **部署**：改 env 后重启服务（`docker compose ... up -d` 或 reload）。
4. **可选**：简单问答不需要复合拆解时可关 `COMPOUND_INTENT_ENABLED=false`，少一次 `decompose_query` 调用；复杂推理场景再开 `LLM_ENABLE_THINKING=true`。

**标签**：`config`
