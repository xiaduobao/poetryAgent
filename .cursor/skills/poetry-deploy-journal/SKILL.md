---
name: poetry-deploy-journal
description: >-
  Auto-save user Q&A and solved problems to project docs after every reply.
  Use for ANY user question in poetryAgent—deploy, code, config, commands.
  No need for the user to ask "record this"; append to docs automatically.
---

# 自动整理问答到项目文档

## 核心规则（每次对话必做）

用户提问 → 你回答完毕后 → **自动**把本次问答整理写入项目文档。

**用户不需要说「记录一下」「保存」**，这是默认行为。

## 写入哪个文件

| 内容类型 | 目标文件 |
|----------|----------|
| 部署 / ECS / ACR / Docker / Nginx / 环境变量 | `docs/deploy-troubleshooting.md` |
| 其他（代码、命令、架构、本地开发等） | `docs/project-notes.md` |

若一次对话同时涉及两类，两处都写，或只在更贴切的一处写，避免重复。

## 每条记录格式

在对应文件**文末**追加（`project-notes.md` 不存在则创建）：

```markdown
---

## YYYY-MM-DD · 一句话标题

**问**：用户原意（精简，可 paraphrase）

**答**：结论 + 关键命令/配置（3～10 行，可复制执行）

**标签**：`deploy` | `docker` | `rag` | `config` | `other`
```

部署类问题若与 `deploy-troubleshooting.md` 已有章节重复 → **更新原章节**，不新建重复条目。

## 写什么 / 不写什么

| 写 | 不写 |
|----|------|
| 问题现象、根因、解决方案 | API Key、密码、JWT、ACR 凭证 |
| 可复用的命令、配置片段 | 冗长对话原文 |
| 文件路径、版本、日期 | 无实质内容的寒暄 |

## 回答用户时的收尾

正文回答结束后，用一行告知即可：

> 已记入 `docs/project-notes.md`（或 `docs/deploy-troubleshooting.md`）·「标题」

不要为此单独开很长一段。

## 禁止

- 等用户明确要求才记录
- 只口头总结不写文件
- 为每条问答新建独立 md 文件
- 记录密钥到文档
