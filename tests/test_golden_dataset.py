"""Схема golden-набора для eval: валидные регионы и непустые ожидания."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.regions import FEDERAL_CODE, REGIONS

GOLDEN = Path(__file__).resolve().parent.parent / "data" / "eval" / "golden.jsonl"


def _load() -> list[dict]:
    cases = []
    with GOLDEN.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def test_golden_file_exists_and_not_empty() -> None:
    cases = _load()
    assert len(cases) >= 15


def test_golden_cases_have_valid_schema() -> None:
    known_regions = set(REGIONS) | {FEDERAL_CODE}
    seen_ids: set[str] = set()
    for case in _load():
        assert case["id"] not in seen_ids, f"дубль id: {case['id']}"
        seen_ids.add(case["id"])
        assert case["region"] in known_regions, f"{case['id']}: регион {case['region']}"
        assert case["object_type"].strip()
        expected = case.get("expected_sections_any")
        assert expected and all(s.strip() for s in expected), f"{case['id']}: пустые ожидания"


def test_golden_covers_all_regions() -> None:
    covered = {case["region"] for case in _load()}
    assert set(REGIONS).issubset(covered)
    assert FEDERAL_CODE in covered
