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
    exec python -m app.bot.main
fi

alembic upgrade head
exec uvicorn app.api.main:app --host 0.0.0.0 --port "${PORT:-8000}"
