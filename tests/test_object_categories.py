"""Тиры объектов РНГП и multi-query phrases."""

from __future__ import annotations

from app.core.object_categories import (
    query_phrases_for_object,
    tier_for_object,
)


def test_tier_group1_profile_objects() -> None:
    assert tier_for_object("детский сад") == "group1"
    assert tier_for_object("школа") == "group1"
    assert tier_for_object("многоквартирный дом") == "group1"
    assert tier_for_object("жилой дом") == "group1"
    assert tier_for_object("мкд") == "group1"
    assert tier_for_object("поликлиника") == "group1"
    assert tier_for_object("спортивный комплекс") == "group1"


def test_tier_group2_frame_objects() -> None:
    assert tier_for_object("автомойка") == "group2"
    assert tier_for_object("торговый центр") == "group2"
    assert tier_for_object("автосалон") == "group2"
    assert tier_for_object("гостиница") == "group2"
    assert tier_for_object("склад") == "group2"
    assert tier_for_object("медицинский центр") == "group2"
    assert tier_for_object("производство") == "group2"


def test_group1_query_phrases_include_provision_axes() -> None:
    phrases = " ".join(query_phrases_for_object("детский сад")).lower()
    assert "обеспечен" in phrases
    assert "доступност" in phrases


def test_group2_query_phrases_keep_parking_sanitary() -> None:
    phrases = " ".join(query_phrases_for_object("автомойка")).lower()
    assert "парков" in phrases or "машино" in phrases
    assert "санитар" in phrases or "санпин" in phrases


def test_autosalon_query_phrases_like_trade() -> None:
    phrases = " ".join(query_phrases_for_object("автосалон")).lower()
    assert "парков" in phrases or "машино" in phrases
    assert "санитар" in phrases or "санпин" in phrases
    assert "эвакуац" in phrases or "пожар" in phrases
