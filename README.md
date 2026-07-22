# RegioBuild

[English version](README_EN.md)

Сервис справочного сопоставления **региональных нормативов градостроительного
проектирования (РНГП/ТСН)** субъектов Российской Федерации с учётом
федерального нормативного фона (СП 42.13330.2016, выдержки из Федерального
закона от 22.07.2008 № 123-ФЗ, санитарные правила и нормативы).

Ядро решения — HTTP API и RAG-агент на LangGraph: положения в ответе
привязываются к конкретному пункту нормативного акта с разграничением
регионального и федерального уровней. Telegram-клиент служит демонстрационным
интерфейсом; тот же API доступен для внешнего подключения.

Ответ сервиса носит **справочный** характер, не является юридической
консультацией и не подменяет заключение юриста либо проектной организации.

<p align="center">
  <img src="docs/screenshots/01-bot-about.png" alt="RegioBuild — описание в Telegram" width="400"/>
</p>

---

## Назначение

Требования к размещению объектов капитального строительства различаются по
субъектам РФ по содержанию и структуре актов. Ручное сопоставление региональных
РНГП с федеральными нормами трудоёмко и подвержено пропуску существенных
положений.

RegioBuild по запросу (тип объекта и субъект либо два субъекта для сравнения)
формирует обзор применимых фрагментов с указанием пункта и уровня
регулирования. Сервис не оценивает допустимость размещения на конкретном
земельном участке и не учитывает муниципальные ПЗЗ вне текущего индекса.

Правовой статус: [`docs/LEGAL_DISCLAIMER.md`](docs/LEGAL_DISCLAIMER.md).

---

## Возможности

- FastAPI: `/info`, `/compare`, `/api/v1/*`, `/health`, `/metrics`
- Telegram-клиент (aiogram 3)
- Корпус PDF: федеральный слой и РНГП пяти субъектов; иерархический разбор пунктов
- Гибридный retrieval (dense + BM25), grounding цитат, числовой guardrail
- Отказ от выдачи при отсутствии опоры в корпусе

<p align="center">
  <img src="docs/screenshots/02-bot-start.png" alt="Старт: правовой статус" width="360"/>
  &nbsp;
  <img src="docs/screenshots/03-bot-rules.png" alt="Правила работы и дисклеймер" width="360"/>
</p>

---

## Режимы

1. **Обзор по субъекту** — региональные и федеральные требования к объекту
   капитального строительства.
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
полный классификатор объектов капитального строительства.

---

## Стек

| Слой | Состав |
|------|--------|
| Язык | Python 3.11 |
| Backend | FastAPI |
| Клиент | aiogram 3 |
| Оркестрация | LangGraph |
| Embeddings | sentence-transformers (MiniLM; опционально e5-large) |
| Vector DB | Qdrant (основной контур); Chroma — локальный legacy |
| Классификация | scikit-learn (TF-IDF + LogisticRegression) |
| LLM | GigaChat Pro |
| Данные | SQLAlchemy, Alembic |
| Качество | pytest; Recall@k, MRR |
| Инфраструктура | Docker, GitHub Actions, Prometheus, Sentry |

Один Docker-образ; роль процесса задаётся `SERVICE_ROLE=api` либо `bot`.

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

В `.env` указываются учётные данные GigaChat, при необходимости токен бота и
параметры Qdrant (`VECTOR_BACKEND=qdrant`). Для локальной Chroma:
`pip install -r requirements-legacy-chroma.txt`.

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

## Автор

Никита Мокин / Nikita Mokin

[GitHub](https://github.com/NikitaMok) · [LinkedIn](https://ru.linkedin.com/in/mokinnikita)

---

## Права

© Никита Мокин / Nikita Mokin. **Все права защищены.**

Копирование репозитория, воспроизведение существенных частей решения и
использование кода либо продукта в коммерческих целях **без предварительного
письменного согласия правообладателя запрещены**. Размещение исходников на
GitHub предназначено для ознакомления и демонстрации компетенций и не даёт
лицензии на коммерческую эксплуатацию.
