"""Тесты матрицы покрытия волны 1 и honest fallback."""

from __future__ import annotations

import json
from pathlib import Path

from app.agent import nodes
from app.ingestion.federal_sources import all_curated_chunks
from app.vectorstore.types import RetrievedChunk

WAVE1_PATH = Path(__file__).resolve().parent.parent / "app" / "eval" / "datasets" / "wave1_coverage.json"


def test_wave1_curated_sections_present() -> None:
    payload = json.loads(WAVE1_PATH.read_text(encoding="utf-8"))
    by_key = {(c.region_code, c.section_number): c for c in all_curated_chunks()}

    for case in payload["cases"]:
        region = case["region"]
        sections = case["must_find_sections"]
        federal = case.get("federal_sections") or []
        found_regional = [s for s in sections if (region, s) in by_key]
        found_federal = [s for s in federal if ("federal", s) in by_key]
        # секция может быть региональной или федеральной в must_find
        found_any = found_regional or [
            s for s in sections if ("federal", s) in by_key
        ]
        if case.get("must_find_any_of"):
            assert found_any or found_federal, (
                f"{case['id']}: нет curated для {sections} / {federal}"
            )
        else:
            for section in sections:
                assert (region, section) in by_key or ("federal", section) in by_key


def test_filter_usable_chunks_drops_table_junk() -> None:
    chunks = [
        RetrievedChunk(
            id="j",
            text="автомойки | 1 бокс",
            region_code="krasnodar_krai",
            section_number="1",
            category=None,
            distance=0.05,
        ),
        RetrievedChunk(
            id="g",
            text="Пункт 5.5.153 … автомоек",
            region_code="krasnodar_krai",
            section_number="5.5.153",
            category=None,
            distance=0.2,
        ),
    ]
    usable = nodes._filter_usable_chunks(chunks)
    assert len(usable) == 1
    assert usable[0].section_number == "5.5.153"


def test_retrieve_chunks_honest_fallback_when_only_junk(monkeypatch) -> None:
    junk = [
        RetrievedChunk(
            id="j1",
            text="шум таблицы",
            region_code="novosibirsk_oblast",
            section_number="1",
            category=None,
            distance=0.1,
        )
    ]

    monkeypatch.setattr(nodes, "_retrieve_for_region", lambda *a, **k: list(junk))

    state = nodes.retrieve_chunks(
        {
            "mode": "info",
            "business_type": "автомойка",
            "region_a": "novosibirsk_oblast",
        }
    )
    assert state.get("error")
    assert "не найдено проверяемых" in state["error"].lower() or "не найдено" in state["error"].lower()
