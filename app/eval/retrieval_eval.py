"""Запуск: python -m app.eval.retrieval_eval

Считает Recall@k и MRR по датасету app/eval/datasets/retrieval_eval_queries.json.
Часть запросов по Краснодарскому краю пока без эталонных номеров пунктов —
это нужно доразметить руками после первого прогона ingestion-пайплайна,
когда будет видна реальная структура документа. Такие запросы не входят
в усреднение метрик, но их результаты печатаются для ручной проверки.
"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from app.vectorstore.retriever import RetrievedChunk, retrieve

DATASET_PATH = Path(__file__).parent / "datasets" / "retrieval_eval_queries.json"
TOP_K = 5


def _chunk_matches_section(chunk: RetrievedChunk, expected_sections: list[str]) -> bool:
    if not chunk.section_number:
        return False
    return any(
        chunk.section_number == section or chunk.section_number.startswith(section + ".")
        for section in expected_sections
    )


def recall_at_k(results: list[RetrievedChunk], expected_sections: list[str], k: int) -> float:
    if not expected_sections:
        return float("nan")
    top_k = results[:k]
    found = any(_chunk_matches_section(chunk, expected_sections) for chunk in top_k)
    return 1.0 if found else 0.0


def mrr(results: list[RetrievedChunk], expected_sections: list[str]) -> float:
    if not expected_sections:
        return float("nan")
    for rank, chunk in enumerate(results, start=1):
        if _chunk_matches_section(chunk, expected_sections):
            return 1.0 / rank
    return 0.0


def run_eval(top_k: int = TOP_K) -> dict:
    queries = json.loads(DATASET_PATH.read_text(encoding="utf-8"))

    recall_scores = []
    mrr_scores = []

    for query in queries:
        expected_sections = query.get("relevant_section_numbers", [])
        results = retrieve(query["query"], region_code=query.get("region_code"), top_k=top_k)

        if not expected_sections:
            logger.warning(f"нет эталона для запроса {query['query']!r}, результаты для ручной проверки:")
            for chunk in results:
                logger.warning(f"  section={chunk.section_number} dist={chunk.distance:.4f} text={chunk.text[:120]!r}")
            continue

        recall_scores.append(recall_at_k(results, expected_sections, top_k))
        mrr_scores.append(mrr(results, expected_sections))

    avg_recall = sum(recall_scores) / len(recall_scores) if recall_scores else float("nan")
    avg_mrr = sum(mrr_scores) / len(mrr_scores) if mrr_scores else float("nan")

    logger.info(f"Recall@{top_k} = {avg_recall:.3f} ({len(recall_scores)} запросов с эталоном)")
    logger.info(f"MRR = {avg_mrr:.3f} ({len(mrr_scores)} запросов с эталоном)")

    return {"recall_at_k": avg_recall, "mrr": avg_mrr, "k": top_k, "n_evaluated": len(recall_scores)}


if __name__ == "__main__":
    run_eval()
