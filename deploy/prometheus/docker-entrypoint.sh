#!/bin/sh
set -eu

FALLBACK="/etc/prometheus/prometheus.yml"
OUT="/tmp/prometheus.yml"

if [ -z "${GRAFANA_CLOUD_PROMETHEUS_URL:-}" ] \
  || [ -z "${GRAFANA_CLOUD_PROMETHEUS_USER:-}" ] \
  || [ -z "${GRAFANA_CLOUD_PROMETHEUS_TOKEN:-}" ]; then
  echo "WARN: GRAFANA_CLOUD_* не заданы — remote_write отключён" >&2
  cp "$FALLBACK" "$OUT"
else
  # Пишем конфиг целиком: sed ломается на спецсимволах в токене
  cat > "$OUT" <<EOF
global:
  scrape_interval: 30s
  evaluation_interval: 30s
  external_labels:
    project: regiobuild
    env: production

alerting:
  alertmanagers:
    - static_configs:
        - targets: ["alertmanager:9093"]

rule_files:
  - /etc/prometheus/alert_rules.yml

scrape_configs:
  - job_name: regiobuild-api
    metrics_path: /metrics
    static_configs:
      - targets: ["api:3000"]
        labels:
          service: api

remote_write:
  - url: ${GRAFANA_CLOUD_PROMETHEUS_URL}
    basic_auth:
      username: "${GRAFANA_CLOUD_PROMETHEUS_USER}"
      password: "${GRAFANA_CLOUD_PROMETHEUS_TOKEN}"
EOF
  echo "INFO: remote_write → Grafana Cloud включён" >&2
fi

exec /bin/prometheus \
  --config.file="$OUT" \
  --storage.tsdb.retention.time=30d \
  --web.enable-lifecycle \
  "$@"
