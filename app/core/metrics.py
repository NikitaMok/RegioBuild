"""Prometheus-метрики уровня ядра (LLM-экономика).

HTTP-метрики собирает prometheus_fastapi_instrumentator в app.api.main;
здесь — счётчики, к которым обращаются провайдеры LLM.
"""

from __future__ import annotations

from prometheus_client import Counter

LLM_TOKENS = Counter(
    "regiobuild_llm_tokens_total",
    "Токены LLM по данным usage провайдера",
    ["provider", "kind"],  # kind: prompt | completion
)

LLM_REQUESTS = Counter(
    "regiobuild_llm_requests_total",
    "Запросы к LLM",
    ["provider", "outcome"],  # outcome: ok | error
)


def observe_llm_usage(provider: str, prompt_tokens: int | None, completion_tokens: int | None) -> None:
    if prompt_tokens:
        LLM_TOKENS.labels(provider=provider, kind="prompt").inc(prompt_tokens)
    if completion_tokens:
        LLM_TOKENS.labels(provider=provider, kind="completion").inc(completion_tokens)
