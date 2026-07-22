"""Прогон golden-набора (пункты НПА / faithfulness), когда готов golden.json.

Запуск:
  python -m scripts.eval_golden --golden app/eval/datasets/golden.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from loguru import logger

BASE = Path(__file__).resolve().parent.parent


def run(golden_path: Path) -> int:
    if not golden_path.exists():
        logger.error(
            f"нет файла {golden_path}. Положите golden.json в указанный путь — "
            "тогда считаем метрики по пунктам и faithfulness."
        )
        return 2
    payload = json.loads(golden_path.read_text(encoding="utf-8"))
    cases = payload.get("cases") or payload.get("questions") or []
    logger.info(f"загружено кейсов: {len(cases)} — полный прогон требует живой API/LLM")
    logger.info("скелет готов; полный eval — после появления датасета")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--golden",
        type=Path,
        default=BASE / "app" / "eval" / "datasets" / "golden.json",
    )
    args = parser.parse_args()
    raise SystemExit(run(args.golden))


if __name__ == "__main__":
    main()
