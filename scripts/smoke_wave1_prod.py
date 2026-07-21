"""Smoke волны 1 против прод-API Bothost.

Примеры:
  python -m scripts.smoke_wave1_prod --api-url https://bot-xxx-yyy-nikitamok.bothost.tech
  python -m scripts.smoke_wave1_prod --api-url https://... --full

Без --full: только /health.
С --full: info-запросы (тратит токены GigaChat).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

CASES = (
    {
        "id": "carwash_kk",
        "business_type": "автомойка",
        "region_code": "krasnodar_krai",
        "must_any": ("5.5.153", "табл.108", "7.1.3"),
    },
    {
        "id": "warehouse_so",
        "business_type": "склад",
        "region_code": "sverdlovsk_oblast",
        "must_any": ("123-ФЗ", "СанПиН", "СП 42", "пожарн", "санитар"),
    },
)


def _get(url: str, timeout: float = 30.0) -> tuple[int, str]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return int(resp.status), body


def _post_json(url: str, payload: dict, timeout: float = 180.0) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return int(resp.status), json.loads(body) if body else {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke RegioBuild API (волна 1)")
    parser.add_argument("--api-url", required=True, help="Базовый URL API без хвоста /")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Плюс /info кейсы волны 1 (нужен живой GigaChat)",
    )
    args = parser.parse_args()
    base = args.api_url.rstrip("/")

    print(f"health -> {base}/health")
    try:
        status, body = _get(f"{base}/health")
    except urllib.error.HTTPError as exc:
        print(f"FAIL health HTTP {exc.code}")
        return 1
    except Exception as exc:
        print(f"FAIL health: {exc}")
        return 1

    if status != 200 or "ok" not in body.lower():
        print(f"FAIL unexpected health body: {body!r}")
        return 1
    print(f"OK health: {body.strip()}")

    try:
        m_status, _ = _get(f"{base}/metrics", timeout=15.0)
        print(f"metrics HTTP {m_status}")
    except Exception as exc:
        print(f"WARN metrics: {exc}")

    if not args.full:
        print("smoke_wave1_prod: OK (health only; add --full for /info)")
        return 0

    failures = 0
    for case in CASES:
        print(f"\ncase {case['id']}...")
        try:
            status, payload = _post_json(
                f"{base}/info",
                {
                    "business_type": case["business_type"],
                    "region_code": case["region_code"],
                    "telegram_user_id": "smoke-wave1",
                },
            )
        except Exception as exc:
            print(f"FAIL {case['id']}: {exc}")
            failures += 1
            continue

        text = (payload.get("response_text") or "") + " " + (payload.get("error") or "")
        print(f"  HTTP {status}, chars={len(text)}, error={payload.get('error')!r}")
        if status != 200:
            failures += 1
            continue
        if payload.get("error"):
            print(f"  WARN agent error (honest fallback possible): {payload['error'][:200]}")
        lowered = text.lower()
        if any(token.lower() in lowered for token in case["must_any"]):
            print(f"  OK markers {case['must_any']}")
        else:
            print(f"  FAIL no expected markers {case['must_any']}")
            failures += 1
            print(f"  preview: {text[:400]}")

    if failures:
        print(f"\nsmoke_wave1_prod: FAIL ({failures})")
        return 1
    print("\nsmoke_wave1_prod: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
