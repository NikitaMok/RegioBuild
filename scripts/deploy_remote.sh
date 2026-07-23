#!/usr/bin/env bash
# Деплой на VPS: git pull + docker compose up.
# На сервере: /opt/regiobuild, рядом .env (секреты не в git).
set -euo pipefail

ROOT="${DEPLOY_PATH:-/opt/regiobuild}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
cd "$ROOT"

git fetch origin
git reset --hard "origin/${DEPLOY_BRANCH:-main}"

if [[ ! -f .env ]]; then
  echo "нет $ROOT/.env — скопируйте секреты перед деплоем" >&2
  exit 1
fi

# HA: COMPOSE_PROFILES=ha и nginx default.ha.conf
if [[ "${COMPOSE_PROFILES:-}" == *ha* ]]; then
  cp -f deploy/nginx/default.ha.conf deploy/nginx/default.conf
fi

docker compose -f "$COMPOSE_FILE" --env-file .env pull || true
docker compose -f "$COMPOSE_FILE" --env-file .env build
docker compose -f "$COMPOSE_FILE" --env-file .env up -d --remove-orphans

docker compose -f "$COMPOSE_FILE" ps
curl -fsS -m 20 "http://127.0.0.1:3000/health" || curl -fsS -m 20 "http://127.0.0.1/health"
echo
echo "deploy OK"
