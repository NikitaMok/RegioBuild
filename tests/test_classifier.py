from __future__ import annotations

import joblib
import pytest

from app.classifier import predict as predict_module
from app.classifier.train import build_pipeline

# игрушечный пайплайн вместо артефакта из git
TOY_TEXTS = [
    "Срок выдачи разрешения на строительство составляет 10 рабочих дней.",
    "Срок действия технических условий не может быть менее 3 лет.",
    "Заявитель обязан представить пояснительную записку к проекту.",
    "Комплект документов включает градостроительный план земельного участка.",
    "Подключение объекта к сетям водоснабжения выполняется по техническим условиям.",
    "Присоединение к электрическим сетям производится в срок, указанный в договоре.",
]
TOY_LABELS = ["сроки", "сроки", "документы", "документы", "подключение_к_сетям", "подключение_к_сетям"]


@pytest.fixture
def toy_model(tmp_path, monkeypatch):
    model_path = tmp_path / "toy_classifier.joblib"
    pipeline = build_pipeline()
    pipeline.fit(TOY_TEXTS, TOY_LABELS)
    joblib.dump(pipeline, model_path)

    monkeypatch.setattr(predict_module, "MODEL_PATH", model_path)
    predict_module._load_model.cache_clear()
    yield
    predict_module._load_model.cache_clear()


def test_predict_category_returns_one_of_known_labels(toy_model) -> None:
    category = predict_module.predict_category("Срок подключения к сетям составляет 6 месяцев.")
    assert category in TOY_LABELS


def test_predict_categories_preserves_input_order_and_length(toy_model) -> None:
    categories = predict_module.predict_categories(TOY_TEXTS[:3])
    assert len(categories) == 3


def test_predict_with_confidence_returns_valid_probability(toy_model) -> None:
    category, confidence = predict_module.predict_with_confidence(TOY_TEXTS[0])
    assert category in TOY_LABELS
    assert 0.0 <= confidence <= 1.0


def test_predict_without_trained_model_raises_clear_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(predict_module, "MODEL_PATH", tmp_path / "no_such_file.joblib")
    predict_module._load_model.cache_clear()

    with pytest.raises(predict_module.ClassifierNotTrainedError):
        predict_module.predict_category("любой текст")

    predict_module._load_model.cache_clear()
