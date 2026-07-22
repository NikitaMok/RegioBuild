# RegioBuild

[English version](README_EN.md)

Региональные нормативы градостроительного проектирования в РФ — отдельная
вселенная. В каждом субъекте свои требования, своя структура актов, своя
плотность регулирования. Федеральные нормы задают базовый уровень, но
региональная специфика может менять всё: от параметров застройки до санитарных
разрывов.

Сравнивать это вручную — часы работы. И даже когда кажется, что ничего не
пропущено, оказывается, что пропущено. Я знаю это по своему юридическому опыту.

В США строительное регулирование заметно различается между штатами; в субъектах
Российской Федерации картина сходная. Боль ощущают не только застройщики и
девелоперы, но любой, кто планирует объект капитального строительства в новом
регионе.

**RegioBuild** — попытка решить эту задачу инженерно: API-first навигация по
корпусу РНГП/ТСН с федеральным фоном, с обязательной привязкой утверждений к
пункту акта и разделением регионального и федерального уровней.

Telegram — демонстрационный канал. Ядро — HTTP API, к которому можно
подключить внешний клиент.

<p align="center">
  <img src="docs/screenshots/01-bot-about.png" alt="RegioBuild — описание в Telegram" width="400"/>
</p>

---

## Как это устроено

### Ingestion

Региональные акты приходят в разном виде: PDF, HTML, DOCX, таблицы с ложной
нумерацией. Иерархический парсер вытаскивает структурированные требования;
эвристики отсекают шум до того, как он попадёт в индекс. Если не отсечь — в
векторную базу улетит «пункт 1» из подписи к таблице, и retrieval будет кормить
модель этой кашей.

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

### Агент (LangGraph)

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

FastAPI (`/info`, `/compare`, `/api/v1/*`, `/health`, `/metrics`) + aiogram 3 +
Docker. Один образ, роль процесса — `SERVICE_ROLE=api|bot`. Векторный контур —
Qdrant Cloud; embeddings на хостинге с жёстким RAM — ONNX (fastembed), без
PyTorch в runtime. Дисковый кэш LLM — чтобы не оплачивать один и тот же запрос
дважды. Prometheus и Sentry — по конфигурации окружения.

### Оценка качества

Recall@k и MRR — для retrieval. Pytest в CI (облегчённый прогон без torch).
Smoke после выкладки — проверка, что контур жив, без ручного «тыканья» вслепую.

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

## Охват корпуса

| ISO 3166-2 | Субъект |
|------------|---------|
| `RU-MOS` | Московская область |
| `RU-KDA` | Краснодарский край |
| `RU-SVE` | Свердловская область |
| `RU-NVS` | Новосибирская область |
| `RU-TA` | Республика Татарстан |
| `RU-FED` | Федеральный уровень (СП 42, выдержки 123-ФЗ / СанПиН и др.) |

Индекс ограничен этим корпусом и не претендует на полный свод СП РФ или полный
классификатор объектов.

---

## Статус

**Рабочий прототип.** Полный цикл: ingestion → индекс → агент → API → Telegram.

**Сделано**

- citation grounding и числовой guardrail  
- гибридный retrieval, Qdrant, ISO-регионы  
- классификатор категорий требований  
- Docker, CI, метрики, тесты, smoke  
- API-first контур (`/api/v1`) рядом с Telegram-демо  

**Дальше**

- расширение охвата (регионы, при необходимости муниципальный слой)  
- устойчивость к нетипичным формулировкам  
- обновление корпуса при изменении НПА  
- снижение латентности ответа (кэш, профилирование)  
- более плотный мониторинг и алертинг  

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
| Инфраструктура | Docker, GitHub Actions, Prometheus, Sentry |

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
