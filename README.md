# RegioBuild

[English version](README_EN.md)

Различия в региональных нормативах градостроительного проектирования в
Российской Федерации — известная проблема, которую почти невозможно закрыть
вручную. В каждом субъекте свои требования, своя структура актов и плотность
регулирования. Федеральные нормы задают базовый уровень, но региональная
специфика может изменить всё.

Я знаю это по своему юридическому опыту. Сравнивать требования вручную — часы
работы даже для опытного юриста. И когда кажется, что ничего не пропущено,
часто как раз что-то уходит из поля зрения.

**RegioBuild** — инженерное решение этой задачи.

<p align="center">
  <img src="docs/screenshots/01-bot-about.png" alt="RegioBuild — описание в Telegram" width="400"/>
</p>

---

## Что это такое

Сервис анализа региональных нормативов градостроительного проектирования
(РНГП/ТСН) с учётом федерального фона. По запросу (тип объекта и субъект РФ —
либо два субъекта для сравнения) возвращает структурированный обзор с привязкой
к пунктам нормативных актов и явным разделением регионального и федерального
уровней.

Telegram на этом этапе — демонстрационный канал. Ядро — **HTTP API**
(`/info`, `/compare`, `/api/v1/*`, `/health`, `/metrics`): внешние системы
подключаются независимо от мессенджера.

---

## Как это работает

### Ingestion

Региональные акты поступают в разных форматах: PDF, HTML, DOCX, таблицы с
ложной нумерацией. Иерархический парсер извлекает структурированные требования;
эвристики отсекают шум до попадания в индекс. Без этого в векторную базу
улетает «пункт 1» из подписи к таблице — и retrieval кормит модель этой кашей.

Манифест корпуса и ISO-коды субъектов — в `config/documents.yaml` и
`config/regions.yaml`. Муниципальные ПЗЗ в текущий индекс не входят.

### Retrieval

Пользователь пишет «автомойка». В нормативах это может быть «автомоечный пост»,
«предприятие по мойке автотранспорта» или строка в таблице. Один semantic search
с этим не справляется.

Пайплайн нормализует тип объекта, расширяет запрос и ищет гибридно: dense
(Qdrant + fastembed/ONNX на проде) и BM25 по кандидатам. Ранжирование учитывает
качество секции: curated-фрагменты и точечная нумерация приоритетнее шума.
Федеральный слой (`RU-FED`) подмешивается явно, без подмены регионального акта.

Классификатор (TF-IDF + LogisticRegression) направляет требования по категориям
коммерческого ответа. Опорный holdout — порядка 88% accuracy на размеченной
выборке.

### Grounding

Самый дорогой сценарий отказа в LegalTech — уверенная выдумка номера пункта.
Здесь это закрыто программно: каждый пункт, который модель предлагает включить в
ответ, сверяется с retrieved-фрагментами. Нет совпадения — пункта в ответе нет.
Пустой retrieval — честный отказ, без «нормы от себя». Дополнительно — числовой
guardrail по цифрам в тексте ответа.

### LangGraph-агент

Узлы управляют процессом end-to-end:

1. нормализация типа объекта  
2. понимание запроса и режима (обзор / сравнение)  
3. query transform  
4. retrieval  
5. классификация требований и rerank  
6. генерация с grounding и форматирование ответа  

LLM вынесен за абстракцию провайдера: в проде GigaChat Pro; YandexGPT в коде
есть, failover по умолчанию выключен — без переписывания графа.

### Production

FastAPI + aiogram 3 + Docker. Один образ, роль процесса — `SERVICE_ROLE=api|bot`.
Векторный контур — Qdrant Cloud; embeddings на хостинге с жёстким лимитом RAM —
ONNX (fastembed), без PyTorch в runtime. Дисковый кэш LLM — чтобы не оплачивать
один и тот же запрос дважды.

### Observability

Для коммерческого контура важны не только ответы, но и наблюдаемость:

- Prometheus-метрики на `GET /metrics` (в т.ч. `regiobuild_guardrail_blocks_total`,
  latency и HTTP-ошибки через instrumentator)
- Grafana Cloud: креды remote write / scrape в env, описание пайплайна —
  [`docs/GRAFANA.md`](docs/GRAFANA.md)
- Sentry — по `SENTRY_DSN`

Метрики и дашборд-контур заложены в продукт; подключение scrape или Alloy remote
write к публичному API завершает связку Cloud ↔ runtime.

Прод на VPS (nginx, бэкапы, Prometheus/Alertmanager, CI/CD по SSH):  
[`docs/PRODUCTION.md`](docs/PRODUCTION.md). Чеклист Bothost (демо):  
[`docs/BOTHOST_CHECKLIST.md`](docs/BOTHOST_CHECKLIST.md).

### Качество

Hit rate = доля кейсов, где хотя бы один ожидаемый `section_number` попал в
retrieval-контекст агента (`python -m scripts.eval_golden`, режим retrieval).
Это **не** «юридически верный ответ» и не разрешение строить объект — только
метрика якорей. Дисклеймер: [`docs/LEGAL_DISCLAIMER.md`](docs/LEGAL_DISCLAIMER.md).

Цели: **100** кейсов в `data/eval/golden.jsonl`, hit rate **≥ 95%** (стремиться
к 99%). Порог в `eval_golden` для retrieval — 0.95.

LLM: `temperature=0.0` на всех вызовах (нормализация, extraction, compare) —
детерминированные ответы по НПА.

Текущий честный прогон (`fastembed` + Qdrant, полный корпус, без force-inject
и без search только по CURATED):

| Набор | Hit rate | Смысл |
|--------|----------|--------|
| `data/eval/golden.jsonl` | **100/100** | диагностика якорей (фиксированные типы) |
| `data/eval/blind_paraphrase.jsonl` | **60/60** | слепые формулировки юриста/строителя в пилотном скоупе |

Главная метрика устойчивости в скоупе — **blind**, не golden.
Цель: blind ≥ 90% на корректных запросах пилотных типов × регионов.

Безопасный контур ответа: citation grounding + numeric guardrail; при пустой
или слабой опоре — **отказ**, а не список неподтверждённых требований.

**Не обещаем:** юридическую верность ответа «как у юриста на участке» на
произвольном тексте. Hit rate ≠ разрешение строить. Возможное будущее
коммерческого контура — человеческая верификация / расширенный answer-eval
(не текущий DoD).

Прогон blind:
`python -m scripts.eval_golden --golden data/eval/blind_paraphrase.jsonl`

Pytest в CI (облегчённый прогон без torch). Smoke после выкладки — проверка,
что контур жив, без ручного «тыканья» вслепую.

Архитектура: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).  
Выкладка: [`docs/BOTHOST_CHECKLIST.md`](docs/BOTHOST_CHECKLIST.md).

<p align="center">
  <img src="docs/screenshots/02-bot-start.png" alt="Старт бота" width="360"/>
  &nbsp;
  <img src="docs/screenshots/03-bot-rules.png" alt="Ограничения использования" width="360"/>
</p>

---

## Режимы

1. **Обзор по субъекту** — региональные и федеральные требования к объекту.  
2. **Сравнение двух субъектов** — различия и совпадения с указанием пунктов.

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

## Интеграция (API v1)

Коммерческий контур — `/api/v1` с аутентификацией по `X-API-Key` и
машиночитаемым ответом: каждое требование привязано к пункту НПА, уровню
регулирования (региональный/федеральный) и дате сверки документа с
первоисточником. Интерактивная спецификация — `GET /docs` (OpenAPI).

Выпуск ключа клиенту (на сервере):

```bash
python -m scripts.manage_api_keys create --name "ООО Клиент" --daily-limit 200
```

Запрос:

```bash
curl -X POST https://<host>/api/v1/info \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rgb_…" \
  -d '{"region": "RU-KDA", "object_type": "автомойка"}'
```

Ответ (сокращённо):

```json
{
  "region": "RU-KDA",
  "object_type": "автомойка",
  "guardrail_blocked": false,
  "requirements": [
    {
      "category": "градостроительные",
      "description": "Для автомоек принимается 1 машино-место на 1 бокс.",
      "is_specific": true,
      "citation": {
        "document": "Постановление №78",
        "clause": "табл.108",
        "region": "RU-KDA",
        "level": "regional",
        "last_verified": "2026-07-22"
      }
    }
  ],
  "sources": [
    {"region": "RU-KDA", "title": "…", "url": "https://…", "last_verified": "2026-07-22"}
  ]
}
```

`/api/v1/compare` дополнительно возвращает `differences` (значения по двум
регионам с отдельными цитатами) и `common_requirements`. Пример клиента —
[`examples/api_client.py`](examples/api_client.py).

Масштабирование на новые субъекты РФ — процедура без изменения кода:
[`docs/ADDING_REGION.md`](docs/ADDING_REGION.md).

---

## Охват корпуса

| ISO 3166-2 | Субъект |
|------------|---------|
| `RU-MOS` | Московская область |
| `RU-KDA` | Краснодарский край |
| `RU-SVE` | Свердловская область |
| `RU-NVS` | Новосибирская область |
| `RU-TA` | Республика Татарстан |
| `RU-FED` | Федеральный слой: ГрК РФ, СП 42, 123-ФЗ, СанПиН (полный парc PDF в индексе) |

Индекс ограничен этим корпусом и не претендует на полный свод всех СП РФ или
полный классификатор объектов. ПЗЗ / муниципальный уровень вне скоупа.

---

## Статус

**Рабочий прототип.** Полный цикл: ingestion → индекс → агент → API → Telegram.

**Сделано**

- citation grounding и числовой guardrail  
- гибридный retrieval, Qdrant, ISO-регионы  
- классификатор категорий требований  
- Docker, CI, метрики Prometheus, Grafana Cloud (контур), тесты, smoke  
- API-first рядом с Telegram-демо  

**Что можно улучшить**

- расширение охвата (регионы, муниципальный уровень)  
- устойчивость к нетипичным формулировкам  
- обновление корпуса при изменении НПА  
- снижение латентности ответа (кэш, профилирование)  
- полный scrape / remote write метрик в Grafana Cloud на проде  

---

## Стек

| Слой | Состав |
|------|--------|
| Язык | Python 3.11 |
| Backend | FastAPI |
| Клиент | aiogram 3 |
| Оркестрация | LangGraph |
| Embeddings | fastembed (ONNX); опционально sentence-transformers |
| Vector DB | Qdrant (основной); Chroma — локальный legacy |
| Классификация | scikit-learn (TF-IDF + LogisticRegression) |
| LLM | GigaChat Pro |
| Данные | SQLAlchemy, Alembic |
| Observability | Prometheus `/metrics`, Grafana Cloud, Sentry |
| Инфраструктура | Docker, GitHub Actions |

---

## Репозиторий и запуск

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

```bash
python -m venv venv
venv\Scripts\activate          # Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env         # Linux/Mac: cp .env.example .env
```

В `.env` — учётные данные GigaChat, при необходимости токен бота, параметры
Qdrant и (опционально) Grafana Cloud. Для локальной Chroma:
`pip install -r requirements-legacy-chroma.txt`.

```bash
alembic upgrade head
python -m scripts.parse_pdf_docs   # при наличии data/raw/docs
python -m scripts.index_qdrant

uvicorn app.api.main:app --reload
python -m app.bot.main
```

Либо `docker compose up --build`. Прод на VPS:
`docker compose -f docker-compose.prod.yml --env-file .env up -d --build`
(см. [`docs/PRODUCTION.md`](docs/PRODUCTION.md)). Postgres: `docker-compose.postgres.yml`.

```bash
pytest
python -m app.eval.retrieval_eval
python -m app.eval.answer_eval
```

Smoke после выкладки: `python -m scripts.smoke_wave1_prod --api-url https://…`.

---

## Ограничения использования

RegioBuild — справочный инструмент, а не юридическая консультация. Ответы не
заменяют проектную документацию, заключение юриста или проверку актуальности
нормативов на момент решения. Муниципальные ПЗЗ в индекс не включены — их нужно
проверять отдельно.

Подробнее: [`docs/LEGAL_DISCLAIMER.md`](docs/LEGAL_DISCLAIMER.md).

---

© Никита Мокин / Nikita Mokin.  
[GitHub](https://github.com/NikitaMok) · [LinkedIn](https://ru.linkedin.com/in/mokinnikita)

Все права защищены. Копирование репозитория, воспроизведение существенных частей
решения и использование кода либо продукта в коммерческих целях без
предварительного письменного согласия правообладателя запрещены. Размещение
исходников на GitHub предназначено для ознакомления и демонстрации компетенций
и не даёт лицензии на коммерческую эксплуатацию.
