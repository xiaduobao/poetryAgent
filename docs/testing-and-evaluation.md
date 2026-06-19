# 测试与 RAG 评估

> 返回 [文档首页](README.md)

## pytest

```bash
# 需先 pip install -r requirements.txt
pytest tests/ -v
pytest tests/ -v --cov=app --cov-fail-under=40   # 与 CI 一致
```

测试覆盖：JWT 认证、输入安全、意图规则、会话 CRUD、Chat/RAG API（Mock LLM，不消耗 API Key）。

## Pre-commit

与 CI lint 一致，提交前自动检查：

```bash
pip install pre-commit   # 已含在 requirements.txt
pre-commit install       # 安装 git hook（仅需一次）

# 手动跑全量 lint（等同 CI 的 ruff + frontend eslint）
pre-commit run --all-files
```

- 改动 `app/` 或 `tests/` 下 Python 文件 → `ruff check app tests`
- 改动 `frontend/` → `cd frontend && npm run lint`

## RAG 检索评估

### 简易关键词检查（无需 LLM API）

```bash
python scripts/eval_rag.py
python scripts/eval_rag.py --golden tests/eval/rag_golden_set.json
python scripts/eval_rag.py --output reports/rag_eval.json   # 写入指标报告
```

### Ragas 全链路评估（需 `OPENAI_API_KEY`）

```bash
pip install -r requirements-eval.txt \
  -i https://pypi.tuna.tsinghua.edu.cn/simple --default-timeout=120
python scripts/eval_rag_ragas.py
python scripts/eval_rag_ragas.py --retrieval-only   # 仅评检索（ContextRecall）
python scripts/eval_rag_ragas.py --output reports/ragas.json
```

| 脚本 | 指标 | 说明 |
|------|------|------|
| `eval_rag.py` | 召回数、关键词命中 | 离线 smoke test，适合 CI |
| `eval_rag_ragas.py` | Faithfulness、AnswerRelevancy、ContextRecall、FactualCorrectness | 基于 [Ragas](https://docs.ragas.io/)，用 LLM 评判回答质量 |

Golden set 位于 `tests/eval/rag_golden_set.json`（**30 条**：20 首单篇赏析 + 10 条主题/体裁查询），每条含 `query`、`reference`（参考答案）及可选 `author` 过滤。

### 当前评估结果（2026-06-19）

基于 **202 篇语料**、已构建向量库，运行 `python scripts/eval_rag.py`：

| 指标 | 数值 | 说明 |
|------|------|------|
| Golden set 规模 | 30 条 | 单篇赏析 20 + 主题/体裁 10 |
| 检索通过率 | **100%**（30/30） | `min_docs` 达标且 `expect_keywords` 命中 |
| 平均召回篇数 | **3.33** 篇/查询 | 混合检索 + Rerank 后 Top-K |
| 语料规模 | 202 篇 | `data/corpus/*.md` |

结构化报告：[reports/rag_eval.json](../reports/rag_eval.json)

> 全链路生成质量（Faithfulness、AnswerRelevancy 等）需配置 API Key 后运行 `eval_rag_ragas.py`；指标报告可写入 `reports/ragas.json`。
