"""Минимальный клиент RegioBuild API v1.

Использование:
  python examples/api_client.py --api-url https://<host> --api-key rgb_…
"""

from __future__ import annotations

import argparse
import json

import httpx


def info(api_url: str, api_key: str, region: str, object_type: str) -> dict:
    response = httpx.post(
        f"{api_url}/api/v1/info",
        headers={"X-API-Key": api_key},
        json={"region": region, "object_type": object_type},
        timeout=180,
    )
    response.raise_for_status()
    return response.json()


def compare(api_url: str, api_key: str, region_a: str, region_b: str, object_type: str) -> dict:
    response = httpx.post(
        f"{api_url}/api/v1/compare",
        headers={"X-API-Key": api_key},
        json={"region_a": region_a, "region_b": region_b, "object_type": object_type},
        timeout=180,
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--api-key", required=True)
    args = parser.parse_args()

    result = info(args.api_url, args.api_key, region="RU-KDA", object_type="автомойка")
    print(f"требований: {len(result['requirements'])}")
    for item in result["requirements"]:
        cite = item["citation"]
        print(f"- [{item['category']}] {item['description']}")
        print(f"  источник: {cite['document']}, п. {cite['clause']} ({cite['level']})")

    diff = compare(
        args.api_url, args.api_key, region_a="RU-MOS", region_b="RU-SVE", object_type="склад"
    )
    print(f"\nсравнение: {diff['summary']}")
    print(f"различий: {len(diff['differences'])}, совпадений: {len(diff['common_requirements'])}")


if __name__ == "__main__":
    main()
