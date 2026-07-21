"""Запуск: python -m app.eval.answer_eval

В отличие от retrieval_eval.py, здесь проверяется итоговый ответ агента:
есть ли цитаты источника, упомянуты ли нужные регионы, покрыты ли ожидаемые
категории требований. Прогонять этот скрипт стоит после любых изменений
промптов или логики агента, чтобы сразу заметить регресс.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from app.agent.graph import run_compare_query, run_info_query
from app.core.regions import get_region

DATASET_PATH = Path(__file__).parent / "datasets" / "answer_eval_questions.json"
RESULTS_PATH = Path(__file__).parent / "datasets" / "answer_eval_last_run.json"

CITATION_PATTERN = re.compile(r"п\.\s*\S+")


@dataclass
class CaseResult:
    id: str
    passed: bool
    no_error: bool
    mentions_region: bool
    has_citation: bool
    category_coverage: float
    notes: list[str] = field(default_factory=list)


def _run_case(case: dict) -> CaseResult:
    notes = []

    if case["mode"] == "info":
        agent_state = run_info_query(case["business_type"], case["region_a"])
        expected_region_names = [get_region(case["region_a"]).display_name]
    else:
        agent_state = run_compare_query(case["business_type"], case["region_a"], case["region_b"])
        expected_region_names = [
            get_region(case["region_a"]).display_name,
            get_region(case["region_b"]).display_name,
        ]

    answer = agent_state.get("response_text", "")
    error = agent_state.get("error")

    no_error = error is None
    if not no_error:
        notes.append(f"ошибка агента: {error}")

    mentions_region = all(name in answer for name in expected_region_names)
    if not mentions_region:
        notes.append("в ответе нет упоминания всех ожидаемых регионов")

    has_citation = bool(CITATION_PATTERN.search(answer))
    if not has_citation:
        notes.append("в ответе нет цитат вида 'п. ...'")

    expected_categories = case.get("expected_categories", [])
    from app.agent.nodes import CATEGORY_LABELS

    def _category_mentioned(category: str) -> bool:
        label = CATEGORY_LABELS.get(category, category.replace("_", " ")).lower()
        needle = category.replace("_", " ").lower()
        lowered = answer.lower()
        return label in lowered or needle in lowered

    covered = sum(1 for category in expected_categories if _category_mentioned(category))
    category_coverage = covered / len(expected_categories) if expected_categories else 1.0
    if category_coverage < 1.0:
        notes.append(f"покрыто {covered}/{len(expected_categories)} ожидаемых категорий")

    passed = no_error and mentions_region and has_citation and category_coverage > 0

    return CaseResult(
        id=case["id"],
        passed=passed,
        no_error=no_error,
        mentions_region=mentions_region,
        has_citation=has_citation,
        category_coverage=category_coverage,
        notes=notes,
    )


def run_eval() -> dict:
    cases = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    results = []

    for case in cases:
        logger.info(f"кейс {case['id']} ({case['mode']}, {case['business_type']})")
        try:
            result = _run_case(case)
        except Exception as exc:
            logger.error(f"кейс {case['id']} упал с исключением: {exc}")
            result = CaseResult(
                id=case["id"], passed=False, no_error=False, mentions_region=False,
                has_citation=False, category_coverage=0.0, notes=[str(exc)],
            )
        results.append(result)
        logger.info(f"  {'OK' if result.passed else 'FAIL'}: {result.notes or 'без замечаний'}")

    passed_count = sum(1 for r in results if r.passed)
    summary = {
        "total": len(results),
        "passed": passed_count,
        "pass_rate": passed_count / len(results) if results else 0.0,
        "avg_category_coverage": sum(r.category_coverage for r in results) / len(results) if results else 0.0,
        "cases": [r.__dict__ for r in results],
    }

    RESULTS_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"pass rate: {summary['passed']}/{summary['total']} ({summary['pass_rate']:.0%})")

    return summary


if __name__ == "__main__":
    run_eval()
