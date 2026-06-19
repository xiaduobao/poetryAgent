# poetryAgent 架构与流程图

> 古典诗词鉴赏智能助手 · React 前端 + FastAPI 后端 + LangGraph Agent + RAG + 工具链  
> 线上站点：[https://cnpoetry.top/](https://cnpoetry.top/) · 返回 [文档首页](README.md)

---

## 1. 系统总览

```mermaid
flowchart TB
    subgraph Client["前端 React 19 + Vite"]
        UI[AppLayout / Chat UI]
        AuthCtx[AuthContext JWT]
        Hooks[useSessions / useChatStream]
        UI --> AuthCtx --> Hooks
    end

    subgraph Gateway["FastAPI 网关层"]
        MW[中间件: CORS / RequestId / Metrics / SecurityHeaders]
        RL[限流 slowapi]
        SEC[输入安全 filter]
        MW --> RL --> SEC
    end

    subgraph API["API 路由 /api/v1"]
        AuthR[/auth/* JWT 登录刷新/]
        SessionR[/sessions/* 会话 CRUD/]
        ChatR[/chat / chat/stream SSE/]
        RagR[/rag 纯检索/]
        ToolR[/tools/* 直接调工具/]
        AdminR[/admin/* 管理/]
        CorpusR[/corpus/* 语料/]
    end

    subgraph Core["核心业务"]
        Agent[LangGraph Agent]
        RAG[RAG 混合检索]
        Tools[7 个 Function Tools]
        LLM[通义千问 DashScope]
    end

    subgraph Data["数据层"]
        PG[(PostgreSQL / SQLite)]
        Redis[(Redis 可选)]
        Chroma[(Chroma 向量库)]
        Corpus[data/corpus/*.md]
        Authors[data/authors.json]
    end

    subgraph Obs["可观测性"]
        LS[LangSmith 追踪]
        Prom[Prometheus /metrics]
        Sentry[Sentry]
    end

    Client -->|HTTP/SSE + JWT| Gateway
    Gateway --> API
    ChatR --> Agent
    RagR --> RAG
    ToolR --> Tools
    Agent --> RAG
    Agent --> Tools
    Agent --> LLM
    RAG --> Chroma
    RAG --> Corpus
    Tools --> Corpus
    Tools --> Authors
    SessionR --> PG
    ChatR --> PG
    Agent -->|Checkpoint| Redis
    Agent -->|Checkpoint| PG
    Core --> Obs
```

---

## 2. 一次聊天请求的完整流程（SSE 流式）

```mermaid
sequenceDiagram
    actor User as 用户
    participant FE as React 前端
    participant API as FastAPI /chat/stream
    participant Auth as JWT + 配额
    participant DB as PostgreSQL/SQLite
    participant Agent as LangGraph Agent
    participant RAG as 混合检索
    participant LLM as 通义千问

    User->>FE: 输入问题
    FE->>API: POST /chat/stream (Bearer JWT)
    API->>Auth: 校验 token + 套餐配额
    API->>DB: 保存 user 消息
    API-->>FE: SSE status: classifying

    API->>Agent: prepare_agent()
    Agent->>Agent: classify_intent (规则 → LLM 兜底)

    alt intent = rag
        Agent->>RAG: hybrid_retrieve
        RAG-->>Agent: 文档 + source_refs
        API-->>FE: SSE status: retrieving + sources
    else intent = tool_*
        Agent->>LLM: prepare_tool_call
        Agent->>Agent: run_tools (7 工具之一)
        API-->>FE: SSE status: tools
    else intent = chat
        API-->>FE: SSE status: chatting
    end

    API-->>FE: SSE status: generating
    Agent->>LLM: stream_final_answer (astream)
    loop 逐 token
        LLM-->>API: chunk
        API-->>FE: SSE token
    end

    Agent->>Agent: commit_agent_state (Checkpoint)
    API->>DB: 保存 assistant 消息 + usage
    API-->>FE: SSE done
```

**SSE 事件类型**：`status` → `subtasks`（复合问题时）→ `sources`（RAG 时）→ `token` → `done`

**复合意图**（`COMPOUND_INTENT_ENABLED=true`）：`decomposing` → 并行子任务 `executing` → `generating` 合成回答。单条消息如「介绍杜甫并赏析《登高》」会拆解为多子任务分别走 RAG/工具，再合成。

---

## 3. LangGraph Agent 工作流

Agent 定义在 `app/agent/graph.py`，核心是 **意图识别 → 三路分支 → LLM 生成**。启用 `COMPOUND_INTENT_ENABLED` 时入口为 `decompose_node`，复合问题经 LangGraph `Send` 并行 `execute_subtask` 后 `merge_subtasks` 合成。

```mermaid
flowchart TD
    Start([用户消息 + thread_id]) --> Classify[classify_intent<br/>规则优先 / LLM 兜底]

    Classify --> Route{route_by_intent}

    Route -->|rag| Retrieve[retrieve_rag<br/>混合检索 + Rerank]
    Retrieve --> GenRAG[generate_rag_answer<br/>或 stream RAG prompt]
    GenRAG --> End([END])

    Route -->|tool_*| PrepTool[prepare_tool_call<br/>LLM bind_tools]
    PrepTool --> HasTool{有 tool_calls?}
    HasTool -->|是| RunTools[run_tools<br/>ToolNode 执行]
    RunTools --> Summarize[generate_tool_summary<br/>整理工具结果]
    HasTool -->|否| Summarize
    Summarize --> End

    Route -->|chat| GeneralChat[general_chat<br/>多轮对话]
    GeneralChat --> End

    End --> Commit[commit_agent_state<br/>写入 Checkpoint]
```

### 意图类型（规则 + LLM）

| 意图 | 触发示例 | 分支 |
|------|----------|------|
| `rag` | 赏析、鉴赏、《诗题》 | RAG → LLM |
| `tool_author` | 介绍杜甫 | 作者工具 |
| `tool_meter` | 分析格律 | 格律工具 |
| `tool_compare` | 李白 vs 杜甫 | 对比工具 |
| `tool_lookup` | 查找原文/注释 | 诗词查找 |
| `tool_theme` | 推荐思乡诗 | 主题推荐 |
| `tool_allusion` | 典故含义 | 典故解释 |
| `tool_writing` | 写一首、仿写 | 创作助手 |
| `chat` | 闲聊 | 直接 LLM |

---

## 4. RAG 检索流水线

```mermaid
flowchart LR
    subgraph Offline["离线建索引 scripts/build_index.py"]
        MD[data/corpus/*.md] --> Chunk[chunker 分块<br/>100 token 重叠]
        Chunk --> Embed[BGE-small-zh Embedding]
        Embed --> Chroma[(Chroma data/chroma_db)]
    end

    subgraph Online["在线检索 HybridRetriever"]
        Query[用户 query] --> Vec[向量检索 Top-K]
        Query --> BM25[BM25 关键词 Top-K]
        Vec --> Merge[合并去重]
        BM25 --> Merge
        Merge --> Filter[可选过滤<br/>author/dynasty/genre]
        Filter --> Rerank[BGE-Reranker 精排]
        Rerank --> Context[format_context<br/>带 [1][2] 引用]
        Context --> LLM[LLM 鉴赏生成]
    end

    Chroma --> Vec
    MD --> BM25
```

---

## 5. 工具链（Function Calling）

```mermaid
flowchart TB
    LLM[LLM prepare_tool_call] --> T{选择工具}

    T --> author[author_query<br/>作者生平]
    T --> meter[meter_analysis<br/>格律分析]
    T --> compare[style_compare<br/>风格对比]
    T --> lookup[poem_lookup<br/>原文/注释/译文]
    T --> theme[theme_recommend<br/>主题推荐]
    T --> allusion[allusion_explain<br/>典故解释]
    T --> writing[writing_assistant<br/>创作指南]

    author --> JSON[data/authors.json]
    lookup --> Corpus[data/corpus/]
    theme --> Corpus
    meter --> Corpus
    allusion --> Corpus
    writing --> Corpus

    author --> Summarize[LLM 整理为自然语言]
    meter --> Summarize
    compare --> Summarize
    lookup --> Summarize
    theme --> Summarize
    allusion --> Summarize
    writing --> Summarize
```

---

## 6. 数据与持久化

```mermaid
flowchart TB
    subgraph Session["会话持久化"]
        Sessions[sessions 表]
        Messages[messages 表]
        Usage[usage 记录 Token]
    end

    subgraph Memory["Agent 多轮记忆"]
        CP1[Postgres Checkpoint<br/>生产优先]
        CP2[Redis Checkpoint<br/>次选]
        CP3[MemorySaver<br/>本地降级]
    end

    subgraph Knowledge["知识库"]
        CorpusMD[Markdown 语料]
        ChromaDB[Chroma 向量]
        AuthorsJSON[authors.json]
    end

    ChatAPI[/chat/stream/] --> Sessions
    ChatAPI --> Messages
    ChatAPI --> Usage
    ChatAPI --> CP1
    CP1 -.降级.-> CP2
    CP2 -.降级.-> CP3

    RAG --> ChromaDB
    RAG --> CorpusMD
    Tools --> CorpusMD
    Tools --> AuthorsJSON
```

### 环境对比

| 环境 | 数据库 | Checkpoint | 限流 |
|------|--------|------------|------|
| 本地开发 | SQLite | MemorySaver | 进程内 |
| Docker/ECS | PostgreSQL | Redis / Postgres | Redis |

---

## 7. 部署架构

```mermaid
flowchart TB
    User[浏览器] --> Nginx[Nginx :80<br/>SSE 反代]
    Nginx --> App[FastAPI App :8000<br/>含 frontend/dist]

    subgraph DockerCompose["docker-compose.dev.yml / docker-compose.prod.yml"]
        App
        PG[(PostgreSQL 16)]
        Redis[(Redis 7)]
    end

    App --> PG
    App --> Redis
    App --> ChromaVol[./data 卷<br/>chroma_db + models]
    App --> DashScope[DashScope API<br/>通义千问]
    App --> LangSmith[LangSmith 可选]
    App --> Sentry[Sentry 可选]
```

---

## 8. 目录与模块对应

```
poetryAgent/
├── frontend/          → React UI（SSE 客户端）
├── app/
│   ├── main.py        → FastAPI 入口 + 中间件 + 路由挂载
│   ├── api/           → chat / sessions / rag / tools
│   ├── auth/          → JWT + 多租户配额
│   ├── agent/         → LangGraph 图 + LLM + Prompt
│   ├── rag/           → 分块 / Embedding / 混合检索 / Rerank
│   ├── tools/         → 7 个业务工具实现
│   ├── db/            → SQLAlchemy 模型 + CRUD
│   ├── security/      → 输入过滤 + 限流
│   └── observability/ → LangSmith / Prometheus / Sentry
├── data/
│   ├── corpus/        → 诗词 Markdown 语料
│   ├── chroma_db/     → 向量库
│   └── authors.json   → 作者库
└── scripts/
    ├── build_index.py → 离线建索引
    └── deploy/        → ECS 部署脚本
```

---

## 9. 启动生命周期

应用启动时（`app/main.py` lifespan）依次：

1. 初始化日志 / Sentry / LangSmith
2. `init_db()` — Alembic 迁移 + 建表
3. `setup_checkpointer()` — Postgres → Redis → MemorySaver
4. `build_vector_store()` — 加载或构建 Chroma

---

## 10. 技术栈速查

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.11 + FastAPI + SQLAlchemy 2.0 异步 |
| 前端 | React 19 + Vite + shadcn/ui + Tailwind + AuthContext |
| 认证 | JWT（access + refresh）+ 多租户配额 |
| 数据 | **生产**：PostgreSQL 16 + Alembic；**本地**：SQLite |
| 缓存/Checkpoint | **生产**：Redis 7；**本地**：MemorySaver 降级 |
| Agent | LangChain + LangGraph |
| RAG | BGE-small-zh + Chroma + BM25 混合检索 + BGE-Rerank |
| LLM | 通义千问（DashScope OpenAI 兼容 API） |
| 可观测 | LangSmith、Prometheus `/metrics`、Sentry、Token 计量 |
| 部署 | Docker Compose（Postgres + Redis + App） |
