#!/usr/bin/env bash
# Деплой на VPS: git pull + docker compose up + обязательная проверка живого runtime.
# На сервере: /opt/regiobuild, рядом .env (секреты не в git).
set -euo pipefail

ROOT="${DEPLOY_PATH:-/opt/regiobuild}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
cd "$ROOT"

git fetch origin
git reset --hard "origin/${DEPLOY_BRANCH:-main}"

EXPECTED_AFTER="$(git rev-parse HEAD)"
echo "deploy target SHA: $EXPECTED_AFTER ($(git rev-parse --short HEAD))"

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
docker compose -f "$COMPOSE_FILE" --env-file .env up -d --remove-orphans --force-recreate api bot

docker compose -f "$COMPOSE_FILE" ps

# Ждём healthy API перед verify
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  if curl -fsS -m 10 "http://127.0.0.1:3000/health" >/dev/null 2>&1; then
    break
  fi
  if [[ "$i" -eq 12 ]]; then
    echo "API не поднялся после up -d" >&2
    exit 1
  fi
  sleep 5
done

export DEPLOY_PATH="$ROOT"
export COMPOSE_FILE
export DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
export EXPECTED_SHA="${EXPECTED_SHA:-$EXPECTED_AFTER}"
bash scripts/verify_deploy.sh

echo "deploy OK (verified)"
