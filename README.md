# 古典诗词鉴赏智能助手

> 个人学习项目 · 诗词知识库 RAG + LangGraph 多轮 Agent + 工具链

## 项目定位

面向古典诗词鉴赏场景，串联 **LangChain、LangGraph、RAG、Chroma、混合检索、Rerank、Function Calling、Prompt 工程、FastAPI、Docker** 的练手与面试演示项目。

## 架构一览

```
用户提问
    ↓
FastAPI (/api/v1/chat)
    ↓
LangGraph Agent
    ├─ 意图识别（规则 + LLM）
    ├─ RAG 分支 → 混合检索(BM25+向量) → BGE-Rerank → LLM 鉴赏
    ├─ 工具分支 → author / meter / compare → LLM 整理
    └─ 闲聊分支
    ↓
多轮记忆（thread_id + MemorySaver）
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.11 + FastAPI |
| Agent | LangChain + LangGraph |
| RAG | BGE-small-zh Embedding + Chroma + BM25 混合检索 + BGE-Rerank |
| 工具 | 作者生平 JSON / 格律分析 / 风格对比 |
| LLM | 通义千问（DashScope OpenAI 兼容 API，默认 `qwen-plus`） |
| 部署 | Docker |

## 快速开始

### 1. 环境准备

**请使用 Python 3.11 或 3.12**。当前 PyTorch 尚未为 **Python 3.13** 提供 macOS/Windows 等平台的预编译包，`sentence-transformers` 会因此无法安装。项目根目录已提供 `.python-version`（pyenv 用户可直接 `pyenv install`）。

```bash
cd poetryAgent
python3.11 -m venv .venv   # 或 python3.12
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，填入 DashScope API Key（OPENAI_API_KEY）
# 可选模型：qwen-turbo / qwen-plus / qwen-max
```

### 2. 构建向量库

```bash
python scripts/build_index.py
```

首次运行会下载 `BAAI/bge-small-zh-v1.5` 与 `BAAI/bge-reranker-base`（需网络）。

**浏览器能打开 [HF-Mirror](https://hf-mirror.com)，但 Python 仍连不上 `huggingface.co` 时**（常见）：

1. 确认 `.env` 中有 `HF_ENDPOINT=https://hf-mirror.com`
2. 用专用脚本经镜像**预下载到本地**（最稳妥）：

```bash
python scripts/download_models.py
# 按脚本输出，把 EMBEDDING_MODEL / RERANK_MODEL 改为 data/models/... 本地路径
python scripts/build_index.py
```

3. 若仍失败，检查终端是否设置了错误代理（与浏览器不一致）：

```bash
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy
export HF_ENDPOINT=https://hf-mirror.com
python scripts/download_models.py
```

4. 或使用 [HF-Mirror 文档](https://hf-mirror.com) 中的 `huggingface-cli download`，下载后把 `.env` 里模型改为本地目录绝对路径。

### 3. 启动服务

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

访问 http://localhost:8000/docs 查看 Swagger。

### 4. Docker 部署

```bash
docker compose up --build
```

## API 示例

### 诗词鉴赏（Agent 自动走 RAG）

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "请赏析《登高》", "thread_id": "user-1"}'
```

### 多轮追问（同一 thread_id）

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "这首诗的名句有哪些？", "thread_id": "user-1"}'
```

### 作者生平

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "介绍杜甫"}'
```

### 格律分析

```bash
curl -X POST http://localhost:8000/api/v1/tools/meter \
  -H "Content-Type: application/json" \
  -d '{"title": "静夜思"}'
```

### 风格对比

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "李白和杜甫的诗歌风格有什么区别？"}'
```

### 纯 RAG 检索

```bash
curl -X POST http://localhost:8000/api/v1/rag \
  -H "Content-Type: application/json" \
  -d '{"query": "表达思乡的诗", "author": "李白"}'
```

## 目录结构

```
poetryAgent/
├── app/
│   ├── main.py           # FastAPI 入口
│   ├── config.py         # 配置
│   ├── api/              # 路由与 Schema
│   ├── rag/              # 分块、Embedding、混合检索、Rerank
│   ├── agent/            # LangGraph 工作流、Prompt、工具绑定
│   ├── tools/            # 作者/格律/对比
│   └── security/         # 输入过滤
├── data/
│   ├── corpus/           # 诗词 Markdown 语料
│   ├── authors.json      # 作者库
│   └── chroma_db/        # 向量库（构建后生成）
├── scripts/
│   ├── build_index.py       # 构建 / 重建向量索引
│   └── generate_corpus.py   # LLM 批量生成语料
├── Dockerfile
└── docker-compose.yml
```

## LLM 批量生成语料

使用 `scripts/generate_corpus.py`，通过通义千问（DashScope）调用 LLM，将结构化 Markdown 写入 `data/corpus/`。

### 前置配置

在 `.env` 中配置（参见 `.env.example`）：

| 变量 | 说明 |
|------|------|
| `OPENAI_API_KEY` | [DashScope API Key](https://dashscope.console.aliyun.com/) |
| `OPENAI_API_BASE` | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `LLM_MODEL` | 默认 `qwen-plus`；可选 `qwen-turbo`、`qwen-max` |

### 推荐：`auto`（无需指定诗名）

由 LLM 从唐宋著名作品中自动选题，再逐首生成语料。**只需指定篇数**，默认 **20 篇**：

```bash
# 默认生成 20 篇，并重建向量索引（推荐一条龙）
python scripts/generate_corpus.py auto --rebuild-index

# 指定篇数
python scripts/generate_corpus.py auto --count 10 --rebuild-index

# 仅预览选题列表，不写文件
python scripts/generate_corpus.py auto --count 5 --dry-run
```

### 其他生成方式

| 子命令 | 适用场景 | 示例 |
|--------|----------|------|
| `single` | 已知诗题、作者，生成单篇 | `python scripts/generate_corpus.py single --title 春望 --author 杜甫 --dynasty 唐 --genre 七言律诗` |
| `batch` | 任务列表 / 文件批量，需指定诗名 | `python scripts/generate_corpus.py batch -f data/poems_batch.example.txt` |
| `theme` | 按主题选题（默认 5 篇） | `python scripts/generate_corpus.py theme --theme 思乡 --count 5` |
| `dynasty` | 按朝代选题（默认 5 篇） | `python scripts/generate_corpus.py dynasty --dynasty 宋 --count 5` |
| `author` | 生成作者资料到 `authors.json` | `python scripts/generate_corpus.py author --name 王维` |

`batch` 补充示例：

```bash
# 命令行多条（诗题,作者[,朝代][,体裁]）
python scripts/generate_corpus.py batch -i "使至塞上,王维,唐,五言律诗" "枫桥夜泊,张继,唐,七言绝句"

# 任务文件（见 data/poems_batch.example.txt），# 开头为注释
python scripts/generate_corpus.py batch --file data/poems_batch.example.txt --rebuild-index
```

### 通用参数

以下参数适用于 `single` / `batch` / `theme` / `dynasty` / `auto`（`author` 仅支持 `--force`）：

| 参数 | 说明 |
|------|------|
| `--count N` | 选题类命令的篇数（`auto` 默认 20，`theme`/`dynasty` 默认 5） |
| `--rebuild-index` | 完成后自动执行 `scripts/build_index.py` 重建向量库 |
| `--dry-run` | 仅选题预览或校验，不写入 `data/corpus/` |
| `--force` | 覆盖已存在的语料文件 |
| `--delay 1.0` | 批量请求间隔（秒），默认 1 |
| `--no-skip` | 不跳过已存在文件（遇同名则报错） |

生成流程简述：`auto` / `theme` / `dynasty` 先由 LLM 输出 JSON 选题列表，再逐首生成含原文、注释、译文、鉴赏的 Markdown；已存在 `诗题-作者.md` 时默认跳过。

## 扩展语料（手动）

在 `data/corpus/` 新增 Markdown，标题格式建议：

```markdown
# 《诗题》-作者-朝代-体裁

## 原文
...

## 鉴赏
...

## 元数据
- 作者：李白
- 朝代：唐
```

然后重新执行 `python scripts/build_index.py`。

## 面试可讲要点

1. **分块策略**：按单首诗词+鉴赏为语义块，100 token 重叠防断裂，标题锚定元数据。
2. **混合检索**：向量语义 + BM25 关键词，合并去重后 BGE-Rerank 精排。
3. **LangGraph**：意图分支、RAG/工具/闲聊三路、MemorySaver 多轮记忆。
4. **幻觉抑制**：系统 Prompt 约束 + 强制引用 [1][2] + 无资料时明确说明。
5. **工程化**：FastAPI 异步、输入校验、Docker 一键演示。

## 许可证

MIT · 学习用途
