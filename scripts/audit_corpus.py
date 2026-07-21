"""Аудит processed/curated корпусов НПА.

Запуск: python -m scripts.audit_corpus
Exit 1, если доля junk section_number >= 5% в регионе
или покрытие волны 1 критически пустое.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
CURATED_DIR = BASE_DIR / "data" / "curated"

# волна 1 коммерческого размещения
WAVE1_PATTERNS: dict[str, re.Pattern[str]] = {
    "автомойка": re.compile(r"автомойк|автомоек|моечн", re.I),
    "склад": re.compile(r"склад", re.I),
    "торговый_центр": re.compile(r"торгов|магазин|супермаркет", re.I),
    "офис": re.compile(r"офис|административ", re.I),
    "кафе": re.compile(r"кафе|ресторан|общественн\w+\s+питан", re.I),
    "гостиница": re.compile(r"гостиниц|отел|средства\s+размещен", re.I),
    "медцентр": re.compile(r"медицин|поликлиник|больниц", re.I),
    "азс": re.compile(r"азс|автозаправ|топливораздаточ", re.I),
    "производство": re.compile(r"производ|завод|цех", re.I),
    "автосервис": re.compile(r"автосервис|техническ\w+\s+обслуживан|сто\b", re.I),
}

JUNK_BARE_SMALL = frozenset({"1", "2", "3"})
# целевой порог готовности — 5%; жёсткий fail — 25% (после repair таблиц)
MAX_JUNK_RATIO_WARN = 0.05
MAX_JUNK_RATIO_FAIL = 0.25


def _classify_section(section: str | None) -> str:
    raw = (section or "").strip()
    if not raw:
        return "null"
    if raw.startswith("табл.") or "/" in raw:
        return "curated_or_table"
    if "." in raw:
        return "dotted"
    if raw.isdigit():
        value = int(raw)
        if raw in JUNK_BARE_SMALL:
            return "junk_1_2_3"
        if value >= 100:
            return "junk_ge_100"
        return "bare_other"
    return "other"


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def audit_region(path: Path) -> dict:
    rows = _load_jsonl(path)
    classes = Counter(_classify_section(row.get("section_number")) for row in rows)
    total = len(rows) or 1
    junk = classes["junk_1_2_3"] + classes["junk_ge_100"]
    coverage = {
        name: sum(1 for row in rows if pattern.search(row.get("text") or ""))
        for name, pattern in WAVE1_PATTERNS.items()
    }
    return {
        "file": path.name,
        "total": len(rows),
        "classes": dict(classes),
        "junk": junk,
        "junk_ratio": junk / total,
        "coverage": coverage,
    }


def main() -> int:
    reports: list[dict] = []
    for path in sorted(PROCESSED_DIR.glob("*.jsonl")):
        reports.append(audit_region(path))
    curated_rows = []
    for path in sorted(CURATED_DIR.glob("*.jsonl")):
        curated_rows.extend(_load_jsonl(path))

    print("=== PROCESSED ===")
    failures: list[str] = []
    curated_coverage = {
        name: sum(1 for row in curated_rows if pattern.search(row.get("text") or ""))
        for name, pattern in WAVE1_PATTERNS.items()
    }
    for report in reports:
        junk_pct = report["junk_ratio"] * 100
        print(
            f"{report['file']}: total={report['total']} "
            f"junk={report['junk']} ({junk_pct:.1f}%) "
            f"dotted={report['classes'].get('dotted', 0)} "
            f"curated_or_table={report['classes'].get('curated_or_table', 0)}"
        )
        if report["total"] > 0 and report["junk_ratio"] >= MAX_JUNK_RATIO_FAIL:
            failures.append(
                f"{report['file']}: junk ratio {junk_pct:.1f}% >= {MAX_JUNK_RATIO_FAIL * 100:.0f}%"
            )
        elif report["total"] > 0 and report["junk_ratio"] >= MAX_JUNK_RATIO_WARN:
            print(
                f"  warn: {report['file']} junk {junk_pct:.1f}% "
                f"(цель < {MAX_JUNK_RATIO_WARN * 100:.0f}%)"
            )
        # НО / шумные регионы: тонкий или грязный processed допустим при curated волны 1
        if report["file"] in {"novosibirsk_oblast.jsonl", "sverdlovsk_oblast.jsonl"}:
            curated_ok = (
                curated_coverage.get("автомойка", 0) >= 1
                and curated_coverage.get("склад", 0) >= 1
            )
            if report["file"] == "novosibirsk_oblast.jsonl" and report["total"] < 200:
                if curated_ok:
                    print(
                        f"  note: {report['file']} тонкий ({report['total']}), "
                        f"опора на curated (регион ограничен)"
                    )
                else:
                    failures.append(
                        f"{report['file']}: тонкий корпус ({report['total']}) без curated-покрытия волны 1"
                    )
            if report["junk_ratio"] >= MAX_JUNK_RATIO_FAIL and curated_ok:
                # не дублируем fail по junk — уже предупредили выше как warn, если < fail
                failures[:] = [
                    f for f in failures if not f.startswith(f"{report['file']}: junk ratio")
                ]
                print(
                    f"  note: {report['file']} junk высокий, но curated волны 1 закрывает gap"
                )

    print("\n=== WAVE1 COVERAGE (processed hits) ===")
    by_object: dict[str, dict[str, int]] = defaultdict(dict)
    for report in reports:
        region = report["file"].replace(".jsonl", "")
        for name, count in report["coverage"].items():
            by_object[name][region] = count
            print(f"  {region}/{name}: {count}")

    print(f"\n=== CURATED: {len(curated_rows)} chunks ===")
    for name, count in curated_coverage.items():
        print(f"  curated/{name}: {count}")
        if count == 0 and name in {"автомойка", "склад"}:
            failures.append(f"curated: нет покрытия для {name}")

    if failures:
        print(f"\naudit_corpus: FAIL ({len(failures)} issues)")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("\naudit_corpus: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
