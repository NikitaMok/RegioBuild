# RegioBuild

[English version](README_EN.md)

Сервис для сопоставления **региональных нормативов градостроительного
проектирования (РНГП/ТСН)** субъектов РФ с учётом федерального фона
(СП 42.13330.2016, выдержки из Федерального закона от 22.07.2008 № 123-ФЗ,
санитарные правила и нормативы).

Ядро — HTTP API и RAG-агент на LangGraph: утверждения в ответе опираются на
конкретный пункт нормативного акта, с разделением регионального и федерального
уровней. Telegram-клиент — демонстрационный интерфейс; тот же API можно
подключить из внешнего сервиса.

<p align="center">
  <img src="docs/screenshots/01-bot-about.png" alt="RegioBuild — описание в Telegram" width="400"/>
</p>

---

## Задача

Требования к размещению объектов капитального строительства в субъектах РФ
сильно различаются по плотности и структуре актов. Ручное сравнение региональных
РНГП с федеральными нормами занимает много времени и легко пропускает существенные
положения.

RegioBuild собирает **справочный обзор** по запросу: тип объекта и субъект
(или два субъекта для сравнения), с указанием пункта и уровня регулирования.
Это не юридическая консультация и не вывод о допустимости размещения на
конкретном участке.

---

## Что реализовано

- Telegram-клиент (aiogram 3) и FastAPI (`/info`, `/compare`, `/api/v1/*`,
  `/health`, `/metrics`)
- Корпус PDF (федеральный слой + РНГП пяти субъектов), иерархический разбор
  пунктов, гибридный retrieval (dense + BM25)
- Векторное хранилище: **Qdrant** (основной контур); Chroma остаётся как
  локальный legacy-вариант
- Привязка цитат к retrieved-фрагментам и проверка чисел в ответе (guardrail)
- Дисклеймер и явный отказ, если опоры в корпусе нет

Сборка — **рабочий прототип**. Муниципальные ПЗЗ в индекс не входят; полнота
по типам объектов и устойчивость на редких формулировках ещё ограничены.

<p align="center">
  <img src="docs/screenshots/02-bot-start.png" alt="Старт: правовой статус" width="360"/>
  &nbsp;
  <img src="docs/screenshots/03-bot-rules.png" alt="Правила работы и дисклеймер" width="360"/>
</p>

Подробнее о правовом статусе: [`docs/LEGAL_DISCLAIMER.md`](docs/LEGAL_DISCLAIMER.md).

---

## Режимы

1. **Обзор по субъекту** — региональные и федеральные требования к объекту
   капитального строительства.
2. **Сравнение двух субъектов** — различия и совпадения с указанием пунктов.

Номер пункта из ответа модели сверяется с фрагментами индекса. Без проверяемой
опоры норма в ответ не попадает.

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

Субъекты в индексе: Московская область, Краснодарский край, Свердловская
область, Новосибирская область, Республика Татарстан (коды ISO 3166-2:
`RU-MOS`, `RU-KDA`, `RU-SVE`, `RU-NVS`, `RU-TA`). Федеральный слой — `RU-FED`.

В манифесте также лежат муниципальные PDF Новосибирска; они **не индексируются**
и зарезервированы на следующий этап.

Индекс не претендует на полный свод СП РФ и полный классификатор объектов.

---

## Стек

| Слой | Состав |
|------|--------|
| Язык | Python 3.11 |
| Backend | FastAPI |
| Клиент | aiogram 3 |
| Оркестрация | LangGraph |
| Embeddings | sentence-transformers (multilingual MiniLM; опционально e5-large) |
| Vector DB | Qdrant (primary), Chroma (legacy) |
| Классификация | scikit-learn (TF-IDF + LogisticRegression) |
| LLM | GigaChat Pro (прод); YandexGPT в коде, failover по умолчанию выключен |
| Данные | SQLAlchemy, Alembic, дисковый кэш LLM |
| Качество | pytest; Recall@k, MRR |
| Инфраструктура | Docker, GitHub Actions, Prometheus, Sentry |

Один Docker-образ, роль процесса: `SERVICE_ROLE=api\|bot`.

Пайплайн: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).  
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

В `.env` — учётные данные GigaChat, при необходимости токен бота, параметры
Qdrant (`VECTOR_BACKEND=qdrant`). Для локальной Chroma дополнительно:
`pip install -r requirements-legacy-chroma.txt`.

```bash
alembic upgrade head
# PDF → structured (при наличии data/raw/docs):
python -m scripts.parse_pdf_docs
# индекс Qdrant:
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

CI (GitHub Actions) гоняет облегчённый набор без torch. Smoke после выкладки:
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
