# 古典诗词鉴赏智能助手

> 已上线运行的 RAG + LangGraph Agent 全栈应用 · [cnpoetry.top](https://cnpoetry.top/)

[![Live](https://img.shields.io/badge/Live-cnpoetry.top-blue?style=flat-square)](https://cnpoetry.top/)
[![GitHub](https://img.shields.io/badge/GitHub-poetryAgent-181717?style=flat-square&logo=github)](https://github.com/xiaduobao/poetryAgent)

## 在线体验

**[https://cnpoetry.top/](https://cnpoetry.top/)** — 注册登录后即可使用：诗词赏析、作者查询、格律分析、看图作诗、SSE 流式对话等。

## 功能演示

<video src="https://github.com/user-attachments/assets/33d2ec4f-bdd1-483a-a16d-7beff677d802" controls width="100%" playsinline poster="docs/materials/poster.png">
  <a href="https://github.com/user-attachments/assets/33d2ec4f-bdd1-483a-a16d-7beff677d802">下载演示视频</a>
</video>

## 项目简介

面向古典诗词鉴赏场景的**端到端 AI 应用**：自建 202 篇语料知识库，混合检索 + Agent 工具链驱动多轮对话，已部署至生产环境并对外提供服务。

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.11 + FastAPI + SQLAlchemy 2.0 异步 |
| 前端 | React 19 + Vite + shadcn/ui + Tailwind |
| Agent | LangGraph 意图路由 + 7 个 Function Calling 工具 |
| RAG | BGE-small-zh + Chroma + BM25 混合检索 + BGE-Rerank |
| 数据 | PostgreSQL 16 + Redis 7 + Alembic |
| LLM | 通义千问（DashScope） |
| 部署 | Docker Compose · 阿里云 ECS · [cnpoetry.top](https://cnpoetry.top/) |

### RAG 检索评估（2026-06-19）

| 指标 | 离线 smoke | Ragas（LLM 评判） |
|------|------------|-------------------|
| Golden set | 30 条 | 30 条 |
| 检索通过率 | **100%**（30/30） | — |
| 平均召回 | **3.33** 篇/查询 | — |
| Context Recall | — | **0.68** |
| 语料规模 | 202 篇 | 202 篇 |

- 离线报告：[reports/rag_eval.json](reports/rag_eval.json)
- Ragas 报告：[reports/ragas.json](reports/ragas.json)（`context_recall`，评判模型 `qwen-turbo`）

详见 [测试与 RAG 评估](docs/testing-and-evaluation.md)。

## 架构

系统由 React 前端、FastAPI 网关、LangGraph Agent、RAG 混合检索、7 类工具链与 PostgreSQL/Redis/Chroma 数据层组成。更细的时序图与模块说明见 **[架构文档](docs/architecture.md)**。

```mermaid
flowchart TB
    subgraph Client["前端 - React 19 + Vite"]
        UI[Chat UI / 会话管理]
        JWT[JWT 认证]
    end

    subgraph Gateway["FastAPI 网关"]
        API["auth, sessions, chat/stream, rag, tools"]
        MW[CORS, 限流, 安全过滤, Metrics]
    end

    subgraph Agent["LangGraph Agent"]
        Intent["意图识别 - 规则 + LLM 融合 + ReAct 兜底"]
        Intent --> Branch{路由}
        Branch -->|rag| RAGPath[混合检索到 LLM 鉴赏]
        Branch -->|tool| ToolPath[7 个 Function Tools]
        Branch -->|chat| ChatPath[多轮闲聊]
        CP[Checkpoint 多轮记忆]
    end

    subgraph RAGBlock["RAG 混合检索"]
        Vec[Chroma 向量 Top-K]
        BM25[BM25 关键词 Top-K]
        Rerank[BGE-Rerank 精排]
        Vec --> Merge[合并去重] --> Rerank
        BM25 --> Merge
    end

    subgraph Data["数据层"]
        PG[(PostgreSQL)]
        Redis[(Redis)]
        Chroma[(Chroma)]
        Corpus[语料 202 篇 + authors.json]
    end

    subgraph LLMBlock["LLM - 通义千问"]
        QW[qwen-plus / qwen-vl-max]
    end

    subgraph Obs["可观测性"]
        LS[LangSmith]
        Prom[Prometheus]
        Sen[Sentry]
    end

    UI --> JWT --> MW --> API
    API --> Intent
    RAGPath --> Vec
    Vec --> Chroma
    Vec --> Corpus
    ToolPath --> Corpus
    RAGPath --> QW
    ToolPath --> QW
    ChatPath --> QW
    CP --> PG
    CP --> Redis
    API --> PG
    Intent --> LS
    MW --> Prom
```

## 文档导航

| 文档 | 说明 |
|------|------|
| **[docs/README.md](docs/README.md)** | 📖 **文档首页** — 完整指引与索引 |
| [architecture.md](docs/architecture.md) | 系统架构、Mermaid 流程图、模块对应 |
| [getting-started.md](docs/getting-started.md) | 本地开发：环境、向量库、前后端启动 |
| [deployment.md](docs/deployment.md) | 阿里云 ECS / ACR 生产部署 |
| [deploy-troubleshooting.md](docs/deploy-troubleshooting.md) | 部署故障排查 |
| [testing-and-evaluation.md](docs/testing-and-evaluation.md) | pytest、pre-commit、RAG 评估 |
| [observability.md](docs/observability.md) | LangSmith 追踪与监控指标 |
| [api-examples.md](docs/api-examples.md) | REST / SSE API 示例 |
| [corpus-management.md](docs/corpus-management.md) | LLM 批量生成语料、手动扩展 |
| [interview-highlights.md](docs/interview-highlights.md) | 技术亮点与面试讲解提纲 |
| [project-notes.md](docs/project-notes.md) | 开发问答与问题记录 |

## 快速开始

```bash
git clone https://github.com/xiaduobao/poetryAgent.git && cd poetryAgent
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --default-timeout=120
cp .env.example .env   # 填入 OPENAI_API_KEY（DashScope）
python scripts/build_index.py
docker compose -f docker-compose.infra.yml up -d
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# 另开终端：cd frontend && npm install && npm run dev → http://localhost:5173
```

完整步骤（模型镜像、依赖排查、Docker 全栈等）见 **[本地开发指南](docs/getting-started.md)**。

## 许可证

MIT License
