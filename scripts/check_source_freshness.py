"""Проверка свежести source_url регионов (HTTP HEAD/GET).

Запуск: python -m scripts.check_source_freshness
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

import requests

from app.core.regions import all_documents

TIMEOUT_SEC = 20


def check_url(url: str) -> tuple[bool, str]:
    try:
        response = requests.head(url, timeout=TIMEOUT_SEC, allow_redirects=True)
        if response.status_code >= 400:
            response = requests.get(url, timeout=TIMEOUT_SEC, stream=True)
        if response.status_code >= 400:
            return False, f"HTTP {response.status_code}"
        return True, f"HTTP {response.status_code}"
    except requests.RequestException as exc:
        return False, str(exc)


def main() -> int:
    print(f"check_source_freshness @ {datetime.now(timezone.utc).isoformat()}")
    failed = 0
    for code, doc in all_documents().items():
        ok, detail = check_url(doc.source_url)
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {code}: last_verified={doc.last_verified} — {detail}")
        if not ok:
            failed += 1
    if failed:
        print(f"итого проблем: {failed}")
        return 1
    print("все источники отвечают")
    return 0


if __name__ == "__main__":
    sys.exit(main())
