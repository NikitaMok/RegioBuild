"""Обучение классификатора из categories.xlsx (Wave 4).

  python -m scripts.train_category_classifier --xlsx path/to/categories.xlsx
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"


def run(xlsx: Path) -> int:
    if not xlsx.exists():
        logger.error(f"нет {xlsx} — пришлите categories.xlsx (~500 размеченных пунктов)")
        return 2
    try:
        import pandas as pd
        from joblib import dump
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import classification_report
        from sklearn.model_selection import train_test_split
        from sklearn.pipeline import Pipeline
    except ImportError as exc:
        logger.error(f"зависимости: {exc}")
        return 1

    df = pd.read_excel(xlsx)
    required = {"text", "category"}
    if not required.issubset(set(c.lower() for c in df.columns)):
        # гибко: clause_number, text, region, category
        cols = {c.lower(): c for c in df.columns}
        if "text" not in cols or "category" not in cols:
            logger.error(f"нужны колонки text, category; есть: {list(df.columns)}")
            return 1
        text_col, cat_col = cols["text"], cols["category"]
    else:
        text_col = next(c for c in df.columns if c.lower() == "text")
        cat_col = next(c for c in df.columns if c.lower() == "category")

    x = df[text_col].astype(str).tolist()
    y = df[cat_col].astype(str).tolist()
    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.2, random_state=42)
    pipe = Pipeline(
        [
            ("tfidf", TfidfVectorizer(max_features=10000, ngram_range=(1, 2))),
            ("clf", LogisticRegression(max_iter=1000, class_weight="balanced")),
        ]
    )
    pipe.fit(x_train, y_train)
    pred = pipe.predict(x_test)
    logger.info("\n" + classification_report(y_test, pred))
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    out = MODELS_DIR / "category_clf.joblib"
    dump(pipe, out)
    logger.info(f"сохранено: {out}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xlsx", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.xlsx))


if __name__ == "__main__":
    main()
