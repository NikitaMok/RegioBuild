# Подключение нового субъекта Российской Федерации

[English version](ADDING_REGION_EN.md)

Новый субъект Российской Федерации подключается конфигурацией и данными, без
изменения кода приложения. Ниже — рабочая процедура, проверенная на пилотных
пяти субъектах.

Муниципальные ПЗЗ, местные нормативы градостроительного проектирования и иные
акты местного уровня **в базу сервиса не включаются**. В корпус принимаются
региональные РНГП/ТСН (и при необходимости региональный градостроительный
закон) плюс федеральный слой `RU-FED`.

## 1. Исходные документы

Положить PDF регионального нормативного правового акта (РНГП/ТСН) в
`data/raw/docs/`. Требования:

- обязателен текстовый слой (отдельного OCR-контура нет);
- актуальная редакция с официального источника (docs.cntd.ru, официальный
  портал правовой информации субъекта);
- муниципальные и иные локальные акты в эту папку для включения в базу сервиса
  не помещать.

## 2. Конфигурация

`config/regions.yaml` — блок субъекта с кодом ISO 3166-2:

```yaml
RU-XXX:
  display_name: "…"
  name_locative: "в …"
  document_title: "Постановление … «Об утверждении нормативов градостроительного проектирования …»"
  source_url: "https://…"
  local_raw_filename: "….pdf"
  fetch_format: pdf
  last_verified: "YYYY-MM-DD"
  aliases: [legacy_name]
```

`config/documents.yaml` — записи документов с `ingest: true`
(региональный уровень — `regulatory_level: regional`).

При необходимости уточнить оси поиска и категорию объекта
(`group1` — профильные объекты РНГП; `group2` — рамочная коммерция) в
`config/object_categories.yaml`.

## 3. Разбор и проверка

```bash
python -m scripts.parse_pdf_docs        # PDF → data/structured/ + chunks
python -m scripts.validate_data         # конфиги и curated согласованы
python -m scripts.audit_corpus          # качество нумерации пунктов в чанках
```

Проверить в `data/structured/_summary.json`: число clauses/chunks нового
субъекта сопоставимо с объёмом документа, таблицы извлечены.

## 4. Curated-якоря (по необходимости)

Если ключевые таблицы (парковка, санитарно-защитные зоны) плохо извлекаются из
PDF — добавить 3–7 записей в `data/curated/*.jsonl` по образцу существующих
(субъект, `section_number`, текст с точными значениями, `business_types`).

## 5. Индексация

```bash
# полная переиндексация (embedding backend должен совпадать с runtime)
EMBEDDING_BACKEND=fastembed VECTOR_BACKEND=qdrant python -m scripts.index_qdrant

# либо доливка без reset
python -m scripts.index_qdrant --no-reset
```

## 6. Оценка качества

Добавить 3–5 контрольных кейсов нового субъекта в `data/eval/golden.jsonl`
(тип объекта + ожидаемые пункты) и прогнать:

```bash
python -m scripts.eval_golden
```

Порог: доля попадания в поиск (retrieval hit rate) ≥ 0.8. Ниже — проверить
качество разбора (`section_number`) и при необходимости добавить curated-якоря.

## 7. Производственная среда

Пуш → выкладка на VPS (`docker-compose.prod.yml`, `scripts/deploy_remote.sh`) →
`scripts/verify_deploy.sh` (`verify OK`) → контрольный запрос по новому субъекту
через `/api/v1/info`.

Субъект появляется в `/regions`, клавиатуре бота и валидации API автоматически —
из `config/regions.yaml`.
