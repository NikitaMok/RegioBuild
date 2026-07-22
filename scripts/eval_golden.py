"""Оценка качества retrieval/grounding на golden-наборе.

Режимы:
  retrieval (по умолчанию) — без LLM: проверяет, что ожидаемые пункты НПА
    попадают в retrieval-контекст агента (hit rate). Нужен доступ к vector store.
  agent — полный прогон агента с LLM: дополнительно считает долю ответов
    с непустыми grounded-требованиями и блокировки guardrail. Тратит токены.

Запуск:
  python -m scripts.eval_golden
  python -m scripts.eval_golden --mode agent --limit 5
  python -m scripts.eval_golden --json-out data/eval/last_run.json
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from loguru import logger

BASE = Path(__file__).resolve().parent.parent
DEFAULT_GOLDEN = BASE / "data" / "eval" / "golden.jsonl"


def load_golden(path: Path) -> list[dict]:
    cases: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def _normalize(section: str) -> str:
    return (section or "").strip().replace(" ", "").lower()


def _retrieved_sections(object_type: str, region: str) -> list[str]:
    """Тот же retrieval-путь, что у агента: регион + федеральный слой."""
    from app.agent.nodes import (
        MAX_FEDERAL_CHUNKS,
        _filter_usable_chunks,
        _retrieve_for_region,
    )
    from app.core.regions import FEDERAL_CODE

    chunks = _filter_usable_chunks(_retrieve_for_region(object_type, region))
    if region != FEDERAL_CODE:
        chunks += _filter_usable_chunks(
            _retrieve_for_region(object_type, FEDERAL_CODE, max_chunks=MAX_FEDERAL_CHUNKS)
        )
    return [c.section_number or "" for c in chunks]


def eval_retrieval(cases: list[dict]) -> dict:
    rows: list[dict] = []
    for case in cases:
        started = time.perf_counter()
        sections = _retrieved_sections(case["object_type"], case["region"])
        latency_ms = int((time.perf_counter() - started) * 1000)
        normalized = {_normalize(s) for s in sections}
        expected = [_normalize(s) for s in case.get("expected_sections_any") or []]
        matched = sorted({e for e in expected if e in normalized})
        hit = bool(matched)
        rows.append(
            {
                "id": case["id"],
                "region": case["region"],
                "object_type": case["object_type"],
                "hit": hit,
                "matched": matched,
                "retrieved_count": len(sections),
                "latency_ms": latency_ms,
            }
        )
        status = "OK " if hit else "MISS"
        logger.info(
            f"[{status}] {case['id']}: matched={matched or '—'} "
            f"retrieved={len(sections)} за {latency_ms} ms"
        )

    total = len(rows)
    hits = sum(1 for r in rows if r["hit"])
    by_region: dict[str, list[bool]] = {}
    for r in rows:
        by_region.setdefault(r["region"], []).append(r["hit"])
    return {
        "mode": "retrieval",
        "total": total,
        "hits": hits,
        "hit_rate": round(hits / total, 3) if total else 0.0,
        "by_region": {
            region: {"total": len(vals), "hits": sum(vals), "hit_rate": round(sum(vals) / len(vals), 3)}
            for region, vals in sorted(by_region.items())
        },
        "cases": rows,
    }


def eval_agent(cases: list[dict]) -> dict:
    """Полный прогон: LLM + grounding. Расходует токены GigaChat."""
    from app.agent.graph import run_info_query

    rows: list[dict] = []
    for case in cases:
        started = time.perf_counter()
        try:
            state = run_info_query(case["object_type"], case["region"])
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[FAIL] {case['id']}: {exc}")
            rows.append({"id": case["id"], "ok": False, "error": str(exc)})
            continue
        latency_ms = int((time.perf_counter() - started) * 1000)
        extraction = state.get("extraction")
        items = list(extraction.items) if extraction else []
        blocked = bool(state.get("guardrail_blocked"))
        error = state.get("error")
        ok = bool(items) and not blocked and not error
        rows.append(
            {
                "id": case["id"],
                "ok": ok,
                "grounded_items": len(items),
                "guardrail_blocked": blocked,
                "error": error,
                "latency_ms": latency_ms,
            }
        )
        logger.info(
            f"[{'OK ' if ok else 'MISS'}] {case['id']}: items={len(items)} "
            f"blocked={blocked} за {latency_ms} ms"
        )

    total = len(rows)
    ok_count = sum(1 for r in rows if r.get("ok"))
    return {
        "mode": "agent",
        "total": total,
        "ok": ok_count,
        "ok_rate": round(ok_count / total, 3) if total else 0.0,
        "guardrail_blocked": sum(1 for r in rows if r.get("guardrail_blocked")),
        "cases": rows,
    }


def _print_summary(report: dict) -> None:
    logger.info("—" * 60)
    if report["mode"] == "retrieval":
        logger.info(f"retrieval hit rate: {report['hits']}/{report['total']} = {report['hit_rate']:.1%}")
        for region, stats in report["by_region"].items():
            logger.info(f"  {region}: {stats['hits']}/{stats['total']} = {stats['hit_rate']:.1%}")
    else:
        logger.info(f"agent ok rate: {report['ok']}/{report['total']} = {report['ok_rate']:.1%}")
        logger.info(f"guardrail blocked: {report['guardrail_blocked']}")


def run(golden_path: Path, mode: str, limit: int | None, json_out: Path | None) -> int:
    if not golden_path.exists():
        logger.error(f"нет файла {golden_path}")
        return 2
    cases = load_golden(golden_path)
    if limit:
        cases = cases[:limit]
    logger.info(f"кейсов: {len(cases)}; режим: {mode}")

    report = eval_agent(cases) if mode == "agent" else eval_retrieval(cases)
    _print_summary(report)

    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"отчёт: {json_out}")

    threshold_ok = (
        report.get("hit_rate", 0) >= 0.8 if mode == "retrieval" else report.get("ok_rate", 0) >= 0.6
    )
    return 0 if threshold_ok else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--mode", choices=["retrieval", "agent"], default="retrieval")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()
    raise SystemExit(run(args.golden, args.mode, args.limit, args.json_out))


if __name__ == "__main__":
    main()
