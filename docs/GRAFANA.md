# Grafana Cloud + RegioBuild

Аккаунт Grafana Cloud уже создан. Метрики отдаёт FastAPI: `GET /metrics`
(Prometheus text format), включая `regiobuild_guardrail_blocks_total`,
`regiobuild_llm_tokens_total{provider,kind}` (экономика: prompt/completion
токены по данным usage) и `regiobuild_llm_requests_total{provider,outcome}`.

## Быстрый старт после onboarding

1. На экране «How do you want to get started?» — **Skip setup** или
   **Visualize existing data**.
2. Connections → Add new connection → **Prometheus**.
3. Варианты доставки метрик:

### A) Scrape публичного Bothost `/metrics`

Если API доступен с интернета:
- Prometheus datasource URL = ваш Grafana Agent / Cloud scraper, target =
  `https://bot-…-….bothost.tech/metrics`

### B) Remote write (рекомендуется)

В Grafana Cloud → Prometheus → **Send Metrics** → скопировать:

- `GRAFANA_CLOUD_PROMETHEUS_URL`
- `GRAFANA_CLOUD_PROMETHEUS_USER`
- `GRAFANA_CLOUD_PROMETHEUS_TOKEN`

Положить в локальный `.env` / `bothost-api.env` (**не коммитить**).

Enterprise compose может поднять Grafana Alloy sidecar, который читает
`http://api:3000/metrics` и пушит в Cloud.

## Дашборд RegioBuild Ops (минимальный набор панелей)

- Request rate (`http_requests_total` / instrumentator)
- Latency p50 / p95
- HTTP 5xx rate
- `regiobuild_guardrail_blocks_total` (block %)
- `/health` up

## Алерты

Локальный стек на VPS: Prometheus + Alertmanager (`docker-compose.prod.yml`),
правила в `deploy/prometheus/alert_rules.yml` (API down, 5xx, spike guardrail).

Внешний контроль: GitHub Actions **Health check** (`HEALTH_URL` + опционально
Telegram `ALERT_TELEGRAM_*`). Подробности — [`docs/PRODUCTION.md`](PRODUCTION.md).

Токены Cloud — только в env, см. `.env.example`.
