"""Ragas 评估模块测试（Mock，不调用 LLM API）。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_build_evaluation_dataset_with_mock_retriever():
    from langchain_core.documents import Document

    from app.eval.ragas_runner import build_evaluation_dataset

    doc = Document(page_content="春眠不觉晓，处处闻啼鸟。", metadata={"title": "春晓"})
    retriever = MagicMock()
    retriever.retrieve.return_value = [doc]

    cases = [
        {
            "query": "请赏析《春晓》",
            "author": "孟浩然",
            "reference": "孟浩然《春晓》是名篇。",
            "response": "《春晓》描写春日清晨。",
        }
    ]

    with patch("app.eval.ragas_runner.get_hybrid_retriever", return_value=retriever):
        rows = build_evaluation_dataset(cases, generate_answers=False)

    assert len(rows) == 1
    assert rows[0]["user_input"] == "请赏析《春晓》"
    assert rows[0]["retrieved_contexts"] == [doc.page_content]
    assert rows[0]["response"] == "《春晓》描写春日清晨。"
    retriever.retrieve.assert_called_once_with(
        "请赏析《春晓》",
        author="孟浩然",
        dynasty=None,
        genre=None,
    )


def test_run_ragas_eval_calls_evaluate():
    from app.eval.ragas_runner import run_ragas_eval

    rows = [
        {
            "user_input": "test",
            "retrieved_contexts": ["ctx"],
            "response": "ans",
            "reference": "ref",
        }
    ]
    mock_result = MagicMock()
    mock_result.scores = {"faithfulness": 0.9}
    mock_llm = MagicMock()
    mock_embeddings = MagicMock()

    with (
        patch("app.eval.ragas_runner.get_llm", return_value=mock_llm),
        patch("app.eval.ragas_runner.get_embeddings", return_value=mock_embeddings),
        patch("ragas.evaluate") as mock_evaluate,
        patch("ragas.EvaluationDataset.from_list", return_value=MagicMock()),
        patch("ragas.llms.LangchainLLMWrapper", return_value=mock_llm),
        patch("ragas.embeddings.LangchainEmbeddingsWrapper", return_value=mock_embeddings),
    ):
        mock_evaluate.return_value = mock_result
        result = run_ragas_eval(rows, retrieval_only=False)

    assert result is mock_result
    mock_evaluate.assert_called_once()
    call_kwargs = mock_evaluate.call_args.kwargs
    assert call_kwargs.get("llm") is not None
    assert call_kwargs.get("embeddings") is not None
    assert len(call_kwargs.get("metrics", [])) >= 2
