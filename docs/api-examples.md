# API 示例

> 返回 [文档首页](README.md) · 在线 Swagger：[cnpoetry.top API](https://cnpoetry.top/docs)（若已暴露）或本地 http://localhost:8000/docs

## 流式对话（SSE）

```bash
curl -N -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{"message": "请赏析《登高》", "session_id": "<uuid>"}'
```

事件类型：`status`（阶段）→ `token`（逐字）→ `done`（完成）。

## 会话管理

```bash
# 新建会话
curl -X POST http://localhost:8000/api/v1/sessions \
  -H "Authorization: Bearer <access_token>"

# 列表 / 搜索
curl "http://localhost:8000/api/v1/sessions?q=登高" \
  -H "Authorization: Bearer <access_token>"

# 重命名
curl -X PATCH http://localhost:8000/api/v1/sessions/<id> \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{"title": "杜甫登高赏析"}'

# 删除
curl -X DELETE http://localhost:8000/api/v1/sessions/<id> \
  -H "Authorization: Bearer <access_token>"
```

## 诗词鉴赏（Agent 自动走 RAG，非流式）

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{"message": "请赏析《登高》", "thread_id": "user-1"}'
```

## 多轮追问（同一 thread_id）

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{"message": "这首诗的名句有哪些？", "thread_id": "user-1"}'
```

## 作者生平

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{"message": "介绍杜甫"}'
```

## 格律分析

```bash
curl -X POST http://localhost:8000/api/v1/tools/meter \
  -H "Content-Type: application/json" \
  -d '{"title": "静夜思"}'
```

## 风格对比

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{"message": "李白和杜甫的诗歌风格有什么区别？"}'
```

## 纯 RAG 检索

```bash
curl -X POST http://localhost:8000/api/v1/rag \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{"query": "表达思乡的诗", "author": "李白"}'
```

## 生产环境

将 `localhost:8000` 替换为 `https://cnpoetry.top` 即可调用线上 API（需有效 JWT）。
