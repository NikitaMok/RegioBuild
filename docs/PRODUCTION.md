# Прод-выкладка RegioBuild (VPS Aeza)

Один сервер (Aeza MSK): nginx → API, Telegram-бот, Prometheus + Alertmanager, еженедельный бэкап SQLite.
Векторный индекс — **Qdrant Cloud** (бэкапится у провайдера Qdrant; локально копируем БД запросов/фидбека и LLM-кэш).

## Быстрый старт на сервере

```bash
git clone https://github.com/NikitaMok/RegioBuild.git /opt/regiobuild
cd /opt/regiobuild
cp .env.example .env   # заполнить секреты
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
curl -sS http://127.0.0.1:3000/health
```

Либо: `bash scripts/deploy_remote.sh` (нужны `.git` и `.env`).

## Балансировка

- По умолчанию: nginx → один `api` (`least_conn`, готов ко второму upstream).
- Два API на одном хосте (осторожно с RAM):  
  `COMPOSE_PROFILES=ha docker compose -f docker-compose.prod.yml --env-file .env up -d`  
  и подменить `deploy/nginx/default.conf` на `default.ha.conf` (делает `deploy_remote.sh` при `COMPOSE_PROFILES=ha`).

Второй **сервер** (отказ площадки) — отдельный VPS + DNS failover / смена `A`-записи; индекс остаётся в Qdrant Cloud, БД поднимается из бэкапа (`python -m scripts.restore_backup … --force`).

## Бэкапы

Контейнер `backup` раз в неделю пишет `/app/data/backups/*.tar.gz` (оставить последние `BACKUP_KEEP`, по умолчанию 8).

Вручную:

```bash
docker compose -f docker-compose.prod.yml exec api python -m scripts.backup --keep 8
docker compose -f docker-compose.prod.yml exec api python -m scripts.restore_backup /app/data/backups/FILE.tar.gz --force
```

## Мониторинг и алерты

- Prometheus: scrape `api:3000/metrics`, правила в `deploy/prometheus/alert_rules.yml`.
- Alertmanager: `deploy/alertmanager/alertmanager.yml`; webhook URL через  
  `ALERT_WEBHOOK_URL=… bash scripts/render_alertmanager_config.sh` и монтирование runtime-файла.
- Снаружи: GitHub Actions `Health check` каждые 15 минут — секрет `HEALTH_URL`  
  (например `http://IP:3000/health`), опционально `ALERT_TELEGRAM_BOT_TOKEN` + `ALERT_TELEGRAM_CHAT_ID`.

## CI/CD

- `CI` — тесты на каждый push/PR.
- `Deploy` — по push в `main`, SSH на VPS. Секреты репозитория:  
  `DEPLOY_HOST`, `DEPLOY_SSH_KEY`, опционально `DEPLOY_USER` (по умолчанию root),  
  `DEPLOY_PATH` (`/opt/regiobuild`), `DEPLOY_PORT`.

## Отказоустойчивость на одном узле

- `restart: unless-stopped` у всех сервисов.
- healthcheck API/nginx: нездоровый контейнер перезапускается Docker’ом.
- Восстановление после потери VPS: новый сервер + `.env` + `restore_backup` + `compose up`  
  (Qdrant Cloud не трогаем).
