#!/bin/sh
# Bothost: один образ, два сервиса. Роль — SERVICE_ROLE (api|bot).
# Персистентность между деплоями — только /app/data (sqlite с фидбеком).
set -e
mkdir -p /app/data

if [ "$SERVICE_ROLE" = "bot" ]; then
    echo "starting telegram bot, API_BASE_URL=${API_BASE_URL:-<not set>}"
    exec python -m app.bot.main
fi

# миграции не должны глушить весь контейнер, если схема уже на месте
if ! alembic upgrade head; then
    echo "WARNING: alembic upgrade head failed — starting api anyway"
fi

# PORT должен совпадать с «Порт веб-приложения» в панели Bothost
echo "starting api on 0.0.0.0:${PORT:-8000} (SERVICE_ROLE=${SERVICE_ROLE:-api})"
exec uvicorn app.api.main:app --host 0.0.0.0 --port "${PORT:-8000}"
