"""Выбор embedding backend без загрузки моделей."""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.embeddings.embedder import resolve_embedding_backend


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_standard_defaults_to_fastembed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOY_PROFILE", "standard")
    monkeypatch.setenv("EMBEDDING_BACKEND", "")
    get_settings.cache_clear()
    assert resolve_embedding_backend() == "fastembed"


def test_legacy_bothost_alias_maps_to_standard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOY_PROFILE", "bothost-demo")
    monkeypatch.setenv("EMBEDDING_BACKEND", "")
    get_settings.cache_clear()
    assert get_settings().deploy_profile == "standard"
    assert resolve_embedding_backend() == "fastembed"


def test_enterprise_defaults_to_sentence_transformers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOY_PROFILE", "enterprise")
    monkeypatch.setenv("EMBEDDING_BACKEND", "")
    get_settings.cache_clear()
    assert resolve_embedding_backend() == "sentence_transformers"


def test_explicit_backend_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOY_PROFILE", "enterprise")
    monkeypatch.setenv("EMBEDDING_BACKEND", "fastembed")
    get_settings.cache_clear()
    assert resolve_embedding_backend() == "fastembed"
