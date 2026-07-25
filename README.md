<p align="center">
  <img src="docs/screenshots/banner.png" alt="RegioBuild" width="720"/>
</p>

# RegioBuild

[English version](README_EN.md)

[![CI](https://github.com/NikitaMok/RegioBuild/actions/workflows/ci.yml/badge.svg)](https://github.com/NikitaMok/RegioBuild/actions/workflows/ci.yml)
[![Deploy](https://github.com/NikitaMok/RegioBuild/actions/workflows/deploy.yml/badge.svg)](https://github.com/NikitaMok/RegioBuild/actions/workflows/deploy.yml)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)

Различия в региональных нормативах градостроительного проектирования в
Российской Федерации практически невозможно закрыть вручную: у каждого
субъекта Российской Федерации своя структура актов, своя плотность
регулирования и свои таблицы.
Федеральные нормы задают базовый уровень, но региональная специфика часто
диктует свои требования.

Мне знакома эта проблематика, так как у меня в прошлом разносторонний
юридический бэкграунд. Даже у опытного юриста сравнение региональных
требований между двумя субъектами Российской Федерации по одному типу
объекта может занимать часы, но даже это не гарантирует 100% точности,
ведь легко пропустить существенный пункт.

**RegioBuild** формирует перечень требований для конкретного субъекта
Российской Федерации при проектировании объекта капитального строительства,
анализируя РНГП/ТСН и федеральный фон, а также сравнивает требования между
двумя субъектами при необходимости.

Telegram в данном случае лишь демонстрационный канал. Ядро продукта —
HTTP API (`/info`, `/compare`, `/api/v1/*`, `/health`, `/metrics`).
Внешние системы подключаются независимо от мессенджера.

**Ограничения использования.** RegioBuild — справочный инструмент, а не
юридическая консультация. Полученные ответы не заменяют проектную
документацию и/или заключение юриста, а также самостоятельную проверку
актуальности нормативов на момент запроса. Муниципальные ПЗЗ в индекс не
включены, поэтому на сегодняшний день их нужно проверять отдельно.
Подробнее можно ознакомиться здесь:
[`docs/LEGAL_DISCLAIMER.md`](docs/LEGAL_DISCLAIMER.md).

---

## Приветственный интерфейс

<p align="center">
  <img src="docs/screenshots/01-bot-start.png" alt="Старт бота" width="360"/>
  &nbsp;
  <img src="docs/screenshots/02-bot-must-read.png" alt="Обязательно к прочтению" width="360"/>
</p>

---

## Примеры запросов

<p align="center">
  <img src="docs/screenshots/03-compare-hotel-1.png" alt="Сравнение: гостиница, часть 1" width="360"/>
  &nbsp;
  <img src="docs/screenshots/04-compare-hotel-2.png" alt="Сравнение: гостиница, часть 2" width="360"/>
</p>

<p align="center">
  <img src="docs/screenshots/05-compare-hotel-3.png" alt="Сравнение: гостиница, часть 3" width="360"/>
</p>

<p align="center">
  <img src="docs/screenshots/06-info-carwash-1.png" alt="Автомойка в Свердловской области" width="360"/>
  &nbsp;
  <img src="docs/screenshots/07-info-carwash-2.png" alt="Федеральный блок и дисклеймер" width="360"/>
</p>

---

## Интерфейс обратной связи

<p align="center">
  <img src="docs/screenshots/08-feedback.gif" alt="Обратная связь в боте" width="420"/>
</p>

---

## Режимы работы

1. **Обзор требований по выбранному субъекту Российской Федерации** —
   региональные и федеральные требования к объекту с указанием пунктов.
2. **Сравнение требований между двумя субъектами Российской Федерации** —
   различия и совпадения в региональных и федеральных требованиях к объекту
   с указанием пунктов.

---

## Нормативный корпус

| ISO 3166-2 | Субъект |
|------------|---------|
| `RU-MOS` | Московская область |
| `RU-KDA` | Краснодарский край |
| `RU-SVE` | Свердловская область |
| `RU-NVS` | Новосибирская область |
| `RU-TA` | Республика Татарстан |
| `RU-FED` | Федеральный слой: ГрК РФ, СП 42, 123-ФЗ, СанПиН |

Индекс ограничен этим корпусом. ПЗЗ и муниципальный уровень вне скоупа.
Архитектура расширяема: новый субъект подключается конфигами и данными —
[`docs/ADDING_REGION.md`](docs/ADDING_REGION.md).

---

## Архитектура решения

Кратко:

1. **Ingestion** — PDF/HTML/DOCX → иерархический разбор → чанки в Qdrant.
2. **Retrieval** — нормализация типа объекта, multi-query, hybrid dense + BM25,
   ранжирование с приоритетом надёжных секций и curated-якорей.
3. **Grounding** — пункт из ответа модели попадает в выдачу только при
   совпадении с retrieved-фрагментами; при слабой опоре — отказ.
4. **Агент** — LangGraph: normalize → understand → retrieve → classify →
   rerank → LLM → format/guardrail.
5. **LLM** — GigaChat Ultra (`GigaChat-3-Ultra`), `temperature=0.0`.

Подробнее: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

Оценка retrieval (якоря `section_number`, не юридическая верность ответа):

| Набор | Hit rate |
|--------|----------|
| `data/eval/golden.jsonl` | 100/100 |
| `data/eval/blind_paraphrase.jsonl` | 60/60 |

---

## Программный интерфейс (API)

Коммерческий контур — `/api/v1` с `X-API-Key` и машиночитаемыми цитатами
(документ, пункт, уровень, дата сверки). Спецификация: `GET /docs`.

```bash
python -m scripts.manage_api_keys create --name "ООО Клиент" --daily-limit 200

curl -X POST https://<host>/api/v1/info \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rgb_…" \
  -d '{"region": "RU-KDA", "object_type": "автомойка"}'
```

Пример клиента: [`examples/api_client.py`](examples/api_client.py).

---

## Производственная среда и мониторинг

Прод: VPS Aeza (Москва), nginx, API, Telegram-бот, Prometheus, Grafana Cloud
(remote_write), Alertmanager, еженедельный бэкап. Выкладка — GitHub Actions →
SSH → `scripts/deploy_remote.sh` + `scripts/verify_deploy.sh` (`verify OK`).

<p align="center">
  <img src="docs/screenshots/11-prometheus-targets.png" alt="Prometheus Targets" width="720"/>
</p>

<p align="center">
  <img src="docs/screenshots/12-prometheus-graph.png" alt="Prometheus Graph" width="720"/>
</p>

<p align="center">
  <img src="docs/screenshots/13-grafana-explore.png" alt="Grafana Cloud Explore" width="720"/>
</p>

<p align="center">
  <img src="docs/screenshots/14-github-actions.png" alt="GitHub Actions" width="640"/>
</p>

<p align="center">
  <img src="docs/screenshots/10-aeza-stats.png" alt="Нагрузка VPS Aeza" width="720"/>
</p>

<p align="center">
  <img src="docs/screenshots/09-gigachat-usage.png" alt="Использование GigaChat Ultra" width="480"/>
</p>

---

## Технологический стек

| Слой | Состав |
|------|--------|
| Язык | Python 3.11 |
| Backend | FastAPI |
| Клиент | aiogram 3 |
| Оркестрация | LangGraph |
| Embeddings | fastembed (ONNX) |
| Vector DB | Qdrant Cloud |
| Классификация | scikit-learn (TF-IDF + LogisticRegression) |
| LLM | GigaChat Ultra |
| Данные | SQLAlchemy, Alembic |
| Observability | Prometheus, Grafana Cloud, Sentry |
| Инфраструктура | Docker, GitHub Actions, VPS Aeza |

---

## Локальный запуск и разработка

```
RegioBuild/
  app/           # agent, api, bot, ingestion, vectorstore, llm
  config/        # regions.yaml, documents.yaml, object_categories.yaml
  docs/
  migrations/
  scripts/
  tests/
  data/          # curated; raw/processed/structured — локально
```

```bash
python -m venv venv
venv\Scripts\activate          # Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env         # Linux/Mac: cp .env.example .env
```

В `.env` — учётные данные GigaChat, при необходимости токен бота и параметры
Qdrant.

```bash
alembic upgrade head
python -m scripts.parse_pdf_docs   # при наличии data/raw/docs
python -m scripts.index_qdrant

uvicorn app.api.main:app --reload
python -m app.bot.main
```

Прод: `docker compose -f docker-compose.prod.yml --env-file .env up -d --build`.

```bash
pytest
python -m scripts.eval_golden
```

---

© Никита Мокин / Nikita Mokin  
[GitHub](https://github.com/NikitaMok) ·
[LinkedIn](https://ru.linkedin.com/in/mokinnikita)

Все права защищены.  
Копирование репозитория, воспроизведение существенных частей решения и
использование кода либо продукта в коммерческих целях без предварительного
письменного согласия правообладателя запрещены.  
Размещение исходников на GitHub предназначено для демонстрации компетенций и
не предоставляет лицензии на их коммерческую эксплуатацию.
