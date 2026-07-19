from __future__ import annotations

from app.llm.schemas import RequirementItem


def test_known_category_is_kept_as_is() -> None:
    item = RequirementItem(category="сроки", description="Срок выдачи — 10 дней.", citation="1.1")
    assert item.category == "сроки"


def test_unknown_category_falls_back_to_other() -> None:
    # LLM время от времени придумывает свою категорию ("парковочные места" и т.п.)
    # вместо одной из пяти разрешённых — раньше это приводило к пустым ответам,
    # теперь такие случаи должны тихо схлопываться в "иные_требования".
    item = RequirementItem(category="парковочные места", description="...", citation="4.5")
    assert item.category == "иные_требования"


def test_is_specific_defaults_to_true_when_llm_omits_it() -> None:
    # старые/некорректные ответы LLM без этого поля не должны ломать парсинг —
    # по умолчанию считаем норму специальной, это безопаснее для отображения
    item = RequirementItem(category="сроки", description="...", citation="1.1")
    assert item.is_specific is True
