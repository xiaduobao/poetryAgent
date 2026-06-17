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

**答**：`.env.prod` 配置的路径与 ECS 上实际目录名不一致。

| 配置（.env.prod） | ECS 实际目录 |
|-------------------|--------------|
| `BAAI--bge-small-zh-v1.5` | `bge-small-zh-v1.5` |
| `BAAI--bge-reranker-base` | **不存在**（需下载同步） |

**快速修复（二选一）**：

```bash
# 方案 A：ECS 上建软链（不改 .env.prod）
ssh -i ~/.ssh/mac_bob.pem root@8.134.168.40
cd /opt/poetry-agent/data/models
ln -sf bge-small-zh-v1.5 BAAI--bge-small-zh-v1.5
cd /opt/poetry-agent && ./scripts/deploy/remote-compose.sh restart
```

```bash
# 方案 B：改 .env.prod 为实际目录名后发布
EMBEDDING_MODEL=./data/models/bge-small-zh-v1.5
./scripts/deploy/deploy.sh --env-only
```

**补全 Rerank 模型**（本地执行后同步）：

```bash
python scripts/download_models.py   # 生成 BAAI--bge-* 目录
./scripts/deploy/deploy.sh --with-data
```

**标签**：`deploy` `data`

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
