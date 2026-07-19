#!/bin/sh
# Точка входа для Bothost: платформа не умеет docker-compose и разворачивает
# только один Dockerfile из корня репозитория. Поэтому api и bot — это два
# отдельных "бота" в панели Bothost, собранных из ОДНОГО и того же образа,
# а роль (что именно запускать) переключается переменной окружения
# SERVICE_ROLE, которую задаёшь в настройках каждого бота отдельно.
#
# /app/data — единственная папка, которую Bothost сохраняет между
# передеплоями (см. документацию Bothost). Держим там sqlite с логом
# фидбека — единственное, что реально меняется в проде между пушами.
set -e
mkdir -p /app/data

if [ "$SERVICE_ROLE" = "bot" ]; then
    echo "starting telegram bot, API_BASE_URL=${API_BASE_URL:-<not set>}"
    exec python -m app.bot.main
fi

alembic upgrade head
# Bothost проксирует на «Порт веб-приложения» из панели; uvicorn должен
# слушать ровно тот же порт. Берём PORT из env (задайте PORT=8000 в
# переменных бота и такой же порт в настройках домена), иначе 502 Bad Gateway.
echo "starting api on 0.0.0.0:${PORT:-8000} (SERVICE_ROLE=${SERVICE_ROLE:-api})"
exec uvicorn app.api.main:app --host 0.0.0.0 --port "${PORT:-8000}"
