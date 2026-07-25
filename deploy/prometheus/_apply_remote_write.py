#!/usr/bin/env python3
"""Собрать prometheus.runtime.yml с remote_write из .env (запуск на VPS)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path("/opt/regiobuild")
ENV_PATH = ROOT / ".env"
OUT = ROOT / "deploy" / "prometheus" / "prometheus.runtime.yml"


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def main() -> None:
    env = load_env(ENV_PATH)
    url = env.get("GRAFANA_CLOUD_PROMETHEUS_URL", "")
    user = env.get("GRAFANA_CLOUD_PROMETHEUS_USER", "")
    token = env.get("GRAFANA_CLOUD_PROMETHEUS_TOKEN", "")
    if not (url and user and token):
        raise SystemExit("GRAFANA_CLOUD_* missing in .env")

    cfg = f"""global:
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
  - url: {url}
    basic_auth:
      username: "{user}"
      password: "{token}"
"""
    OUT.write_text(cfg, encoding="utf-8", newline="\n")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
