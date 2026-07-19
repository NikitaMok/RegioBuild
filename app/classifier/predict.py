from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import joblib
from sklearn.pipeline import Pipeline

MODEL_PATH = Path(__file__).parent / "artifacts" / "requirement_classifier.joblib"


class ClassifierNotTrainedError(RuntimeError):
    pass


@lru_cache
def _load_model() -> Pipeline:
    if not MODEL_PATH.exists():
        raise ClassifierNotTrainedError(
            f"модель не найдена: {MODEL_PATH}. Сначала выполните: python -m app.classifier.train"
        )
    return joblib.load(MODEL_PATH)


def predict_category(text: str) -> str:
    return _load_model().predict([text])[0]


def predict_categories(texts: list[str]) -> list[str]:
    return list(_load_model().predict(texts))


def predict_with_confidence(text: str) -> tuple[str, float]:
    model = _load_model()
    probabilities = model.predict_proba([text])[0]
    best_index = probabilities.argmax()
    return model.classes_[best_index], float(probabilities[best_index])
