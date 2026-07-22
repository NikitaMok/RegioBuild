# Bothost — чеклист выкладки RegioBuild

На Pro обычно хватает. Автодеплой по git push лучше не включать: после пуша
часто нужен recreate ботов, домены API меняются.

Embeddings на Bothost: **fastembed (ONNX)**, без PyTorch. В образе `WARMUP_ON_START=off`
(фоновый прогрев на Bothost часто подвешивает процесс). Модель поднимается на
первом запросе; `/health` должен отвечать сразу после старта uvicorn.

Индекс Qdrant должен быть построен тем же backend (`EMBEDDING_BACKEND=fastembed`).

## Порядок после пуша

1. При смене embedding backend — локально переиндексировать Qdrant Cloud:
   `EMBEDDING_BACKEND=fastembed python -m scripts.index_qdrant`
2. Recreate **только API** (`SERVICE_ROLE=api`).
3. Дождаться `/health` → `{"status":"ok"}` (не запускать два тяжёлых Sync сразу).
4. В логах warmup: `backend=fastembed`, число векторов.
5. Recreate **bot** (`SERVICE_ROLE=bot`) с новым `API_BASE_URL`.
6. Smoke: `python -m scripts.smoke_wave1_prod --api-url https://bot-…-….bothost.tech`

## Env — API

| Переменная | Значение |
|------------|----------|
| `SERVICE_ROLE` | `api` |
| `DATABASE_URL` | sqlite/файл на volume, который не затирается |
| `LLM_PROVIDER` | `gigachat` |
| креды GigaChat | из кабинета GigaChat Pro |
| `VECTOR_BACKEND` | `qdrant` |
| `EMBEDDING_BACKEND` | `fastembed` (явно; так же в образе) |
| `WARMUP_ON_START` | `off` (в образе по умолчанию; `delayed` на Bothost не использовать) |
| `SENTRY_DSN` | если нужен алертинг ошибок |
| `LLM_CACHE_ENABLED` | `true` |
| `LOG_JSON` | по желанию `true` для разбора логов |

Проверки после старта:

- `GET /health` → ok
- `GET /metrics` → Prometheus (если instrumentator в образе)
- Sentry: при заданном DSN в логе есть `Sentry инициализирован`
- RAM API после warmup обычно заметно ниже, чем у torch MiniLM (~150–350 MB порядка)

## Env — Bot

| Переменная | Значение |
|------------|----------|
| `SERVICE_ROLE` | `bot` |
| `TELEGRAM_BOT_TOKEN` | токен BotFather |
| `API_BASE_URL` | `https://bot-…-….bothost.tech` — **только дефисы**, без `/` в конце |

Истина в логе: `starting telegram bot, API_BASE_URL=...`

## Метрики и Grafana Cloud

- API отдаёт `GET /metrics` (Prometheus), в т.ч. `regiobuild_guardrail_blocks_total`.
- Подключение к Grafana Cloud: см. [`docs/GRAFANA.md`](GRAFANA.md).
- Токены Cloud только в env, не в git.

## Qdrant

На Bothost в API env: `VECTOR_BACKEND=qdrant`, `QDRANT_URL`, `QDRANT_API_KEY`,
коллекция `regiobuild_normative`. Локально при необходимости Chroma:
`pip install -r requirements-legacy-chroma.txt` и `VECTOR_BACKEND=chroma`.

Enterprise / torch (e5-large): `pip install -r requirements-enterprise-embeddings.txt`,
`DEPLOY_PROFILE=enterprise`, `EMBEDDING_BACKEND=sentence_transformers`.
