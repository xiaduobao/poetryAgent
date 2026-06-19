# 语料管理

> 返回 [文档首页](README.md)

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

## 手动扩展语料

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

## 评估语料质量

扩展语料后建议：

1. 重建索引：`python scripts/build_index.py`
2. 跑离线评估：`python scripts/eval_rag.py --output reports/rag_eval.json`
3. 必要时补充 golden set：`tests/eval/rag_golden_set.json`

详见 [测试与 RAG 评估](testing-and-evaluation.md)。
