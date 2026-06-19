# 面试与技术亮点

> 返回 [文档首页](README.md) · 线上站点：[cnpoetry.top](https://cnpoetry.top/)

面向 AI 应用 / 后端 / 全栈岗位的讲解提纲，按「问题 → 方案 → 结果」组织。

## 1. RAG：混合检索 + 精排

**可讲问题**：为什么不用纯向量检索？分块怎么做的？

| 点 | 说明 |
|----|------|
| 分块 | 按单首诗词+鉴赏为语义块，100 token 重叠，标题锚定作者/朝代/体裁元数据 |
| 混合检索 | BGE-small-zh 向量 + BM25 关键词，合并去重后 BGE-Rerank 精排 |
| 幻觉抑制 | 系统 Prompt 约束 + 强制 `[1][2]` 引用 + 无资料时明确说明 |
| 量化结果 | 30 条 golden set，离线检索通过率 **100%**，平均召回 **3.33** 篇/查询（202 篇语料） |

详见 [testing-and-evaluation.md](testing-and-evaluation.md)、[architecture.md · RAG 流水线](architecture.md#4-rag-检索流水线)。

## 2. Agent：LangGraph 意图路由

**可讲问题**：用户一句话可能想赏析、查作者、比风格，怎么路由？

| 点 | 说明 |
|----|------|
| 意图识别 | 规则优先 → LLM 兜底 → 规则/suggested 融合；低置信或规则冲突 → **ReAct 有限步兜底** |
| 分支 | RAG 快路径 / 7 个 Function Calling 工具 / 闲聊 |
| 复合问题 | 如「介绍杜甫并赏析《登高》」→ 子任务拆解 + LangGraph `Send` **并行执行** → 合成回答 |
| 上下文 | 分类前 `resolve_poem_context` 增强指代消解（「这首诗」→ 上一轮诗题） |

代码入口：`app/agent/graph.py`、`app/agent/intent_classifier.py`、`app/agent/compound_pipeline.py`。

## 3. 多轮记忆与 Checkpoint 降级

**可讲问题**：SSE 流式对话如何保持多轮上下文？

| 环境 | Checkpoint | 说明 |
|------|------------|------|
| 生产 ECS | PostgreSQL / Redis | LangGraph Checkpoint 持久化 |
| 本地无 Redis | MemorySaver | 进程内降级，开发可用 |

`thread_id` / `session_id` 绑定同一会话；会话消息另存 PostgreSQL `messages` 表。

## 4. 工程化与生产部署

**可讲问题**：怎么从本地开发到线上部署？

| 点 | 说明 |
|----|------|
| 全栈 | React 19 SSE 流式 + FastAPI 异步 + JWT 多租户配额 |
| 数据 | PostgreSQL + Alembic 迁移；Redis 限流与 Checkpoint |
| 可观测 | LangSmith 全链路 Run 树（意图 → RAG/工具 → TTFT）；Prometheus / Sentry |
| 部署 | Docker Compose → 阿里云 ECS + Nginx（SSE 反代）+ ACR 镜像 pull |
| 线上 | **[cnpoetry.top](https://cnpoetry.top/)** |

详见 [deployment.md](deployment.md)、[observability.md](observability.md)。

## 5. 多模态：看图作诗

**可讲问题**：除了文本 RAG 还有什么亮点？

视觉模型（`qwen-vl-max`）理解上传图片 → 画面描述 → 创作 Agent（`writing_assistant`）流式输出诗作。两次 LLM 调用，图片不持久化。

## 6. 常见追问与回答思路

| 追问 | 回答方向 |
|------|----------|
| RAG 召回不准怎么办？ | 调 chunk 重叠、混合检索权重、Rerank Top-K；golden set 回归；必要时 query 改写 |
| 意图识别错了？ | 看 LangSmith `intent_source`；规则负向条件、冲突降置信触发 ReAct |
| 成本怎么控？ | 规则命中跳过 LLM 分类；RAG 快路径；套餐配额 + Token 计量 |
| 若上更大流量？ | 检索结果缓存、异步建索引、Embedding 服务化、读写分离 |

## 7. 简历 bullet 参考

```
• 设计 RAG+Agent 全栈系统：混合检索+Rerank，30 条 golden set 检索通过率 100%
• LangGraph 意图路由（规则+LLM 融合+ReAct 兜底），复合问题并行子任务
• React SSE 流式 + JWT 配额 + PostgreSQL/Redis Checkpoint，部署至 cnpoetry.top
```

## 8. 演示建议

1. 打开 [cnpoetry.top](https://cnpoetry.top/) 问「赏析《登高》」→ 展示流式 + 引用来源
2. 打开 [LangSmith 截图](materials/langsmith.png) 讲 Run 树
3. 打开 [architecture.md](architecture.md) 讲 Mermaid 架构图
