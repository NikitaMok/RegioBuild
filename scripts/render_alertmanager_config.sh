#!/usr/bin/env bash
# Подставляет ALERT_WEBHOOK_URL в конфиг Alertmanager на сервере.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/deploy/alertmanager/alertmanager.yml"
DST="${1:-$ROOT/deploy/alertmanager/alertmanager.runtime.yml}"
URL="${ALERT_WEBHOOK_URL:-http://127.0.0.1:9/regiobuild-alerts}"
sed "s|http://127.0.0.1:9/regiobuild-alerts|${URL}|g" "$SRC" > "$DST"
echo "wrote $DST"
