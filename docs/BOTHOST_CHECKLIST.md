# Bothost — чеклист выкладки RegioBuild

На Pro обычно хватает. Автодеплой по git push лучше не включать: после пуша
часто нужен recreate ботов, домены API меняются.

## Порядок после пуша

1. Recreate **только API** (`SERVICE_ROLE=api`).
2. Дождаться `/health` → `{"status":"ok"}` (не запускать два тяжёлых Sync сразу).
3. В логах warmup: число векторов (с curated).
4. Recreate **bot** (`SERVICE_ROLE=bot`) с новым `API_BASE_URL`.
5. Smoke: `python -m scripts.smoke_wave1_prod --api-url https://bot-…-….bothost.tech`

## Env — API

| Переменная | Значение |
|------------|----------|
| `SERVICE_ROLE` | `api` |
| `DATABASE_URL` | sqlite/файл на volume, который не затирается |
| `LLM_PROVIDER` | `gigachat` |
| креды GigaChat | из кабинета GigaChat Pro |
| `WARMUP_ON_START` | `delayed` (не `immediate` на 2 GB) |
| `WARMUP_DELAY_SEC` | `25` (по умолчанию ок) |
| `SENTRY_DSN` | если нужен алертинг ошибок |
| `LLM_CACHE_ENABLED` | `true` |
| `LOG_JSON` | по желанию `true` для разбора логов |

Проверки после старта:

- `GET /health` → ok
- `GET /metrics` → Prometheus (если instrumentator в образе)
- Sentry: при заданном DSN в логе есть `Sentry инициализирован`

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

## Qdrant (enterprise)

Локально: `docker compose --profile enterprise up -d qdrant`, затем
`VECTOR_BACKEND=qdrant` и `python -m scripts.index_qdrant`.
На Bothost 2 GB — профиль `bothost-demo` с Chroma до выделения ресурсов под Qdrant.
