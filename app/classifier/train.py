"""Запуск: python -m app.classifier.train

Обучает TF-IDF + LogisticRegression на app/classifier/data/labeled_examples.csv
и сохраняет пайплайн в artifacts/requirement_classifier.joblib.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
from loguru import logger
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

DATA_PATH = Path(__file__).parent / "data" / "labeled_examples.csv"
ARTIFACTS_DIR = Path(__file__).parent / "artifacts"
MODEL_PATH = ARTIFACTS_DIR / "requirement_classifier.joblib"

# Минимальный набор стоп-слов: убираем только служебные частицы и предлоги,
# слова типа "должен"/"не" в нормативных формулировках несут смысл и их лучше оставить.
STOP_WORDS = [
    "и", "в", "во", "на", "с", "со", "к", "по", "за", "от", "до", "из", "у",
    "а", "то", "или", "но", "как", "так", "что", "это", "для", "об", "при",
]


def build_pipeline() -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words=STOP_WORDS)),
        ("clf", LogisticRegression(max_iter=1000, class_weight="balanced")),
    ])


def train(test_size: float = 0.2, random_state: int = 42) -> Pipeline:
    data = pd.read_csv(DATA_PATH)
    logger.info(f"примеров: {len(data)}, категорий: {data['category'].nunique()}")
    logger.info(f"распределение по категориям:\n{data['category'].value_counts()}")

    train_texts, test_texts, train_labels, test_labels = train_test_split(
        data["text"], data["category"],
        test_size=test_size, random_state=random_state, stratify=data["category"],
    )

    pipeline = build_pipeline()
    pipeline.fit(train_texts, train_labels)

    predictions = pipeline.predict(test_texts)
    logger.info(f"holdout {test_size:.0%}:\n{classification_report(test_labels, predictions)}")

    # финальную модель обучаем на всём датасете
    final_pipeline = build_pipeline()
    final_pipeline.fit(data["text"], data["category"])

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(final_pipeline, MODEL_PATH)
    logger.info(f"модель сохранена: {MODEL_PATH}")

    return final_pipeline


if __name__ == "__main__":
    train()
