# RegioBuild

[English version](README_EN.md)

**RegioBuild** — API-first сервис навигации по региональным нормативам
градостроительного проектирования (РНГП/ТСН) в сопоставлении с федеральным
нормативным слоем. По запросу (тип объекта капитального строительства и субъект
РФ — либо два субъекта для сравнения) система возвращает структурированный обзор
с привязкой к пункту акта и явным разделением регионального и федерального
уровней регулирования.

Архитектурно ядро — HTTP API и retrieval-агент (LangGraph): поиск по корпусу НПА,
генерация ответа и верификация цитат. Telegram-клиент — демонстрационный канал;
внешние системы подключаются к тем же эндпоинтам.

<p align="center">
  <img src="docs/screenshots/01-bot-about.png" alt="RegioBuild — описание в Telegram" width="400"/>
</p>

---

## Задача

В США требования к размещению объектов существенно различаются между штатами.
В Российской Федерации наблюдается сходная картина: содержание и структура
региональных РНГП/ТСН отличаются от субъекта к субъекту, а сопоставление с
федеральными нормами вручную трудоёмко и легко приводит к пропуску существенных
положений.

Это затрагивает не только застройщиков и девелоперов, но любого, кто планирует
размещение объекта капитального строительства в новом регионе. RegioBuild
закрывает эту практическую задачу: быстрый, проверяемый обзор применимых
фрагментов корпуса с указанием источника.

Подробнее об ограничениях использования:
[`docs/LEGAL_DISCLAIMER.md`](docs/LEGAL_DISCLAIMER.md).

---

## Возможности

- FastAPI: `/info`, `/compare`, `/api/v1/*`, `/health`, `/metrics`
- Telegram-клиент (aiogram 3)
- Корпус PDF (федеральный слой и РНГП пяти субъектов), иерархический разбор пунктов
- Гибридный retrieval (dense + BM25), grounding цитат, числовой guardrail
- Отказ от выдачи при отсутствии опоры в корпусе

<p align="center">
  <img src="docs/screenshots/02-bot-start.png" alt="Старт бота" width="360"/>
  &nbsp;
  <img src="docs/screenshots/03-bot-rules.png" alt="Правила и ограничения" width="360"/>
</p>

---

## Режимы

1. **Обзор по субъекту** — региональные и федеральные требования к объекту.
2. **Сравнение двух субъектов** — различия и совпадения с указанием пунктов.

Номер пункта, предложенный моделью, сверяется с retrieved-фрагментами; без
проверяемой опоры положение в ответ не включается.

<p align="center">
  <img src="docs/screenshots/04-bot-modes.png" alt="Выбор режима" width="360"/>
</p>

<p align="center">
  <img src="docs/screenshots/05-bot-info-avtomoika-kk.png" alt="Автомойка в Краснодарском крае" width="400"/>
</p>

<p align="center">
  <img src="docs/screenshots/06-bot-compare-sklad-rt-mo.png" alt="Сравнение склада: Татарстан и Московская область" width="400"/>
</p>

---

## Охват корпуса

| Код ISO 3166-2 | Субъект |
|----------------|---------|
| `RU-MOS` | Московская область |
| `RU-KDA` | Краснодарский край |
| `RU-SVE` | Свердловская область |
| `RU-NVS` | Новосибирская область |
| `RU-TA` | Республика Татарстан |
| `RU-FED` | Федеральный уровень |

Индекс ограничен указанным корпусом и не претендует на полный свод СП РФ либо
полный классификатор объектов капитального строительства. Муниципальные ПЗЗ в
текущий индекс не входят.

---

## Стек

| Слой | Состав |
|------|--------|
| Язык | Python 3.11 |
| Backend | FastAPI |
| Клиент | aiogram 3 |
| Оркестрация | LangGraph |
| Embeddings | fastembed (ONNX); опционально sentence-transformers |
| Vector DB | Qdrant (основной контур); Chroma — локальный legacy |
| Классификация | scikit-learn (TF-IDF + LogisticRegression) |
| LLM | GigaChat Pro |
| Данные | SQLAlchemy, Alembic |
| Качество | pytest; Recall@k, MRR |
| Инфраструктура | Docker, GitHub Actions, Prometheus, Sentry |

Один Docker-образ; роль процесса: `SERVICE_ROLE=api` либо `bot`.

Архитектура: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).  
Выкладка: [`docs/BOTHOST_CHECKLIST.md`](docs/BOTHOST_CHECKLIST.md).

---

## Структура репозитория

```
RegioBuild/
  app/           # agent, api, bot, ingestion, vectorstore, llm
  config/        # regions.yaml, documents.yaml, object_categories.yaml
  docs/
  migrations/
  scripts/
  tests/
  data/          # curated; raw/processed/structured — локально
  Dockerfile
```

---

## Локальный запуск

```bash
python -m venv venv
venv\Scripts\activate          # Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env         # Linux/Mac: cp .env.example .env
```

В `.env` — учётные данные GigaChat, при необходимости токен бота и параметры
Qdrant (`VECTOR_BACKEND=qdrant`, `EMBEDDING_BACKEND=fastembed`). Для локальной
Chroma: `pip install -r requirements-legacy-chroma.txt`.

```bash
alembic upgrade head
python -m scripts.parse_pdf_docs   # при наличии data/raw/docs
python -m scripts.index_qdrant

uvicorn app.api.main:app --reload
python -m app.bot.main
```

Либо `docker compose up --build`. Postgres: `docker-compose.postgres.yml`.

---

## Тесты

```bash
pytest
python -m app.eval.retrieval_eval
python -m app.eval.answer_eval
```

CI (GitHub Actions) выполняет облегчённый набор без torch. Smoke после выкладки:
`python -m scripts.smoke_wave1_prod --api-url https://…`.

---

© Никита Мокин / Nikita Mokin.  
[GitHub](https://github.com/NikitaMok) · [LinkedIn](https://ru.linkedin.com/in/mokinnikita)

Все права защищены. Копирование репозитория, воспроизведение существенных частей
решения и использование кода либо продукта в коммерческих целях без
предварительного письменного согласия правообладателя запрещены. Размещение
исходников на GitHub предназначено для ознакомления и демонстрации компетенций
и не даёт лицензии на коммерческую эксплуатацию.
