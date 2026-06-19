"""Ragas RAG 评估：基于项目混合检索 + LLM 生成链路。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.llm import get_llm
from app.agent.prompts import RAG_PROMPT, SYSTEM_PROMPT
from app.rag.embedder import get_embeddings
from app.rag.retriever import get_hybrid_retriever


def load_golden_cases(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("golden set 必须是 JSON 数组")
    return data


def generate_rag_answer(query: str, contexts: list[str]) -> str:
    """用项目 RAG Prompt + LLM 生成回答（与 Agent RAG 分支一致）。"""
    llm = get_llm()
    context = "\n\n---\n\n".join(c[:1200] for c in contexts)
    prompt = RAG_PROMPT.format(
        context=context or "（无检索结果）",
        history="（无）",
        question=query,
    )
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ]
    resp = llm.invoke(messages)
    return resp.content if hasattr(resp, "content") else str(resp)


def build_evaluation_dataset(
    cases: list[dict[str, Any]],
    *,
    generate_answers: bool = True,
) -> list[dict[str, Any]]:
    """对 golden set 跑检索（及可选生成），构造 Ragas EvaluationDataset 输入。"""
    retriever = get_hybrid_retriever()
    rows: list[dict[str, Any]] = []

    for case in cases:
        query = case["query"]
        author = case.get("author")
        dynasty = case.get("dynasty")
        genre = case.get("genre")

        docs = retriever.retrieve(
            query,
            author=author,
            dynasty=dynasty,
            genre=genre,
        )
        contexts = [d.page_content for d in docs]

        row: dict[str, Any] = {
            "user_input": query,
            "retrieved_contexts": contexts,
        }
        reference = case.get("reference")
        if reference:
            row["reference"] = reference

        if case.get("response"):
            row["response"] = case["response"]
        elif generate_answers:
            row["response"] = generate_rag_answer(query, contexts)

        rows.append(row)
    return rows


def run_ragas_eval(
    dataset_rows: list[dict[str, Any]],
    *,
    retrieval_only: bool = False,
) -> Any:
    """执行 Ragas evaluate，返回 EvaluationResult。"""
    from ragas import EvaluationDataset, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import (
        AnswerRelevancy,
        ContextRecall,
        FactualCorrectness,
        Faithfulness,
    )

    evaluation_dataset = EvaluationDataset.from_list(dataset_rows)
    evaluator_llm = LangchainLLMWrapper(get_llm())
    evaluator_embeddings = LangchainEmbeddingsWrapper(get_embeddings())

    has_reference = any(r.get("reference") for r in dataset_rows)
    has_response = any(r.get("response") for r in dataset_rows)

    metrics = []
    if retrieval_only or not has_response:
        if has_reference:
            metrics.append(ContextRecall())
    else:
        metrics.append(Faithfulness())
        metrics.append(AnswerRelevancy())
        if has_reference:
            metrics.append(ContextRecall())
            metrics.append(FactualCorrectness())

    if not metrics:
        raise ValueError("数据集缺少 reference 或 response，无法选择 Ragas 指标")

    return evaluate(
        dataset=evaluation_dataset,
        metrics=metrics,
        llm=evaluator_llm,
        embeddings=evaluator_embeddings,
    )


def result_to_dict(result: Any) -> dict[str, float]:
    """将 Ragas EvaluationResult 转为可序列化字典。"""
    if hasattr(result, "scores"):
        raw = result.scores
        if isinstance(raw, dict):
            return {k: round(float(v), 4) for k, v in raw.items()}
    if hasattr(result, "to_pandas"):
        df = result.to_pandas()
        return {col: round(float(df[col].mean()), 4) for col in df.columns}
    return dict(result)
