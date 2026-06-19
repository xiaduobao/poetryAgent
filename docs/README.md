# poetryAgent 文档中心

> 古典诗词鉴赏智能助手 · 用户与开发者指引

## 快速链接

| | |
|---|---|
| **线上站点** | [https://cnpoetry.top/](https://cnpoetry.top/) |
| **GitHub 仓库** | [xiaduobao/poetryAgent](https://github.com/xiaduobao/poetryAgent) |
| **演示视频** | [materials/poetryAgentDemo.mp4](materials/poetryAgentDemo.mp4) |
| **Swagger API** | 本地 [http://localhost:8000/docs](http://localhost:8000/docs) |

## 我是访客 — 想体验产品

1. 打开 **[cnpoetry.top](https://cnpoetry.top/)**
2. 注册账号或使用访客模式（若已开放）
3. 可尝试：
   - 「请赏析《登高》」— RAG 鉴赏 + 来源引用
   - 「介绍杜甫」— 作者工具
   - 「李白和杜甫的风格有什么区别」— 对比工具
   - 上传图片 — 看图作诗（多模态）
4. 观看 [演示视频](materials/poetryAgentDemo.mp4) 了解完整交互

## 我是开发者 — 想本地跑起来

按顺序阅读：

1. **[本地开发指南](getting-started.md)** — Python 环境、向量库、Postgres/Redis、前后端启动
2. **[架构文档](architecture.md)** — 系统总览、Agent 工作流、RAG 流水线（含 Mermaid 图）
3. **[API 示例](api-examples.md)** — curl 调用 chat/stream、sessions、rag、tools
4. **[测试与 RAG 评估](testing-and-evaluation.md)** — pytest、pre-commit、golden set 评估

## 我要部署到生产

1. **[部署指南](deployment.md)** — ECS 初始化、`.env.prod`、ACR 镜像、日常发布
2. **[部署故障排查](deploy-troubleshooting.md)** — 502、RAG 无结果、模型下载失败等

生产站点示例：**[https://cnpoetry.top/](https://cnpoetry.top/)**（`CORS_ORIGINS` 需包含该域名）

## 我要扩展语料 / 调优 RAG

1. **[语料管理](corpus-management.md)** — LLM 批量生成、`data/corpus/` 手动扩展、重建索引
2. **[测试与 RAG 评估](testing-and-evaluation.md)** — `eval_rag.py` 离线评估、Ragas 全链路

当前指标（2026-06-19）：30 条 golden set，检索通过率 **100%**，语料 **202** 篇。报告见 [reports/rag_eval.json](../reports/rag_eval.json)。

## 我要排查 Agent / 监控线上

1. **[可观测性](observability.md)** — LangSmith 配置、Run 树结构、推荐监控指标
2. 参考截图：[materials/langsmith.png](materials/langsmith.png)
3. 开发笔记：[project-notes.md](project-notes.md) — 历史 Q&A 与踩坑记录

## 文档目录

| 文档 | 内容 |
|------|------|
| [architecture.md](architecture.md) | 系统架构、SSE 流程、LangGraph、RAG、部署架构（Mermaid） |
| [getting-started.md](getting-started.md) | 环境准备、建索引、Docker 基础设施、前后端、看图作诗 |
| [deployment.md](deployment.md) | 阿里云 ECS / ACR 部署全流程 |
| [deploy-troubleshooting.md](deploy-troubleshooting.md) | 生产环境故障排查 |
| [testing-and-evaluation.md](testing-and-evaluation.md) | pytest、pre-commit、RAG golden set / Ragas |
| [observability.md](observability.md) | LangSmith、Prometheus、Sentry |
| [api-examples.md](api-examples.md) | REST + SSE API curl 示例 |
| [corpus-management.md](corpus-management.md) | 语料生成与扩展 |
| [interview-highlights.md](interview-highlights.md) | 技术亮点与面试讲解提纲 |
| [project-notes.md](project-notes.md) | 开发问答归档 |

## 演示素材

| 文件 | 说明 |
|------|------|
| [materials/poetryAgentDemo.mp4](materials/poetryAgentDemo.mp4) | 功能演示录屏 |
| [materials/Rag.png](materials/Rag.png) | RAG 检索 / 对话界面截图 |
| [materials/langsmith.png](materials/langsmith.png) | LangSmith Agent 追踪截图 |

## 仓库根目录

项目概览与快速开始见根目录 **[README.md](../README.md)**。
