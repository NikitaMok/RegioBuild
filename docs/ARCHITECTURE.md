# Архитектура RegioBuild

Техническое устройство пайплайна: от НПА до ответа пользователю. Продуктовое
описание — в корневом [`README.md`](../README.md).

## Общая схема

```mermaid
flowchart TD
    User[Пользователь Telegram] --> Bot[aiogram Bot]
    Bot --> API[FastAPI Backend]
    API --> Agent[LangGraph Agent]

    subgraph AgentFlow [LangGraph orchestration]
        N0[normalize_business_type] --> N1[understand_query]
        N1 --> N2[retrieve_chunks]
        N2 --> N3[classify_requirements]
        N3 --> N4[llm_compare_or_extract]
        N4 --> N5[format_response_with_citations]
    end

    N0 --> LLMProvider["LLMProvider: GigaChat / YandexGPT"]
    N2 -- "региональные + федеральные чанки" --> VectorDB[(Chroma)]
    N3 --> Classifier["TF-IDF + LogisticRegression"]
    N4 --> LLMProvider
    N5 --> Grounding[Citation grounding]
    Grounding --> QueryLog[(QueryLog / audit)]

    subgraph Ingestion [Offline пайплайн]
        Scrape[Сбор РНГП + СП 42] --> Parse[Парсинг и антиjunk]
        Parse --> Chunk[Чанкинг по пунктам]
        Chunk --> Embed[sentence-transformers]
        Embed --> VectorDB
        Chunk --> MetaDB[(SQL метаданные)]
        Curated[Curated 123-ФЗ / СанПиН] --> VectorDB
    end
```

## Почему так

- **Retrieval и generation разведены.** Recall@k / MRR и «юридическую читаемость»
  ответа меряем отдельно — иначе непонятно, где чинить: индекс или промпт.
- **`LLMProvider`.** Общий интерфейс под GigaChat и YandexGPT: вендора меняем
  без переписывания графа. В проде по умолчанию GigaChat; failover на Yandex
  не включаем без явной необходимости.
- **`normalize_business_type` до retrieval.** Длинные фразы («требования к
  строительству автомойки…») и падежи плохо матчятся с канцеляритом НПА.
  Сначала извлекаем тип объекта (корни/whitelist), LLM — только если не вышло.
- **Федеральный фон.** СП 42.13330.2016 (и curated-выдержки 123-ФЗ / СанПиН)
  не выбираются как «регион». Приоритет у регионального акта; федеральный
  подмешивается с явной пометкой уровня.
- **Citation grounding.** Пункты из ответа LLM сверяются с retrieved-чанками;
  выдуманные номера отбрасываются. При пустом usable retrieval — честный отказ,
  без галлюцинаций «от себя».
- **API отдельно от бота.** Telegram — один из клиентов. Тот же FastAPI можно
  повесить на веб, B2B-кабинет или чужой продукт.

## Runtime-роли

Один Docker-образ, роль через `SERVICE_ROLE`:

| Роль | Процесс |
|------|---------|
| `api` | FastAPI (`/info`, `/compare`, `/health`, `/metrics`), warmup embeddings |
| `bot` | aiogram long polling → HTTP к API |

Локально удобнее `docker-compose` (два сервиса). На хостинге без compose —
два инстанса одного `Dockerfile`.

## Данные

| Слой | Назначение |
|------|------------|
| `data/raw` | исходники НПА (не в git) |
| `data/processed` | чанки после парсинга (не в git) |
| `data/chroma` | векторный индекс (в git — для сборки образа без переиндекса на слабой VPS) |
| `data/curated` | точечные выдержки (123-ФЗ, СанПиН, региональные якоря) |
| SQL (SQLite/Postgres) | документы, чанки, `query_logs` (audit: секции, latency, feedback) |

## Observability

- Prometheus: `GET /metrics`
- Sentry: по `SENTRY_DSN`
- LLM cache: memory + disk (экономия токенов на повторах)
- Rate limit: дневной лимит на `telegram_user_id`
