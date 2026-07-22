# Подключение нового региона

Архитектура config-driven: новый субъект РФ добавляется данными и конфигами,
без изменения кода. Ниже — полная процедура (проверена на 5 регионах).

## 1. Исходные документы

Положить PDF регионального НПА (РНГП/ТСН, при наличии — региональный
градостроительный закон) в `data/raw/docs/`. Требования:

- текстовый слой обязателен (OCR-пайплайна нет);
- актуальная редакция с официального источника (docs.cntd.ru, официальный
  портал правовой информации региона).

## 2. Конфиги

`config/regions.yaml` — блок региона с ISO-кодом:

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

## 3. Парсинг и валидация

```bash
python -m scripts.parse_pdf_docs        # PDF → data/structured/ + chunks
python -m scripts.validate_data         # конфиги и curated согласованы
python -m scripts.audit_corpus          # доля junk-нумерации в чанках
```

Проверить в `data/structured/_summary.json`: число clauses/chunks нового
региона сопоставимо с объёмом документа, tables подняты.

## 4. Curated-якоря (опционально, но желательно)

Если ключевые таблицы (парковка, СЗЗ) плохо поднимаются из PDF —
добавить 3–7 записей в `data/curated/*.jsonl` по образцу существующих
(регион, `section_number`, текст с точными значениями, `business_types`).

## 5. Индексация

```bash
# полная переиндексация (embedding backend = runtime backend!)
EMBEDDING_BACKEND=fastembed VECTOR_BACKEND=qdrant python -m scripts.index_qdrant

# либо доливка без reset
python -m scripts.index_qdrant --no-reset
```

## 6. Оценка качества

Добавить 3–5 кейсов нового региона в `data/eval/golden.jsonl`
(тип объекта + ожидаемые пункты) и прогнать:

```bash
python -m scripts.eval_golden
```

Порог: retrieval hit rate ≥ 0.8. Ниже — смотреть качество парсинга
(`section_number`), добавлять curated-якоря.

## 7. Прод

Пуш → recreate API на Bothost (см. `docs/BOTHOST_CHECKLIST.md`) →
`/health` → smoke-запрос по новому региону через `/api/v1/info`.

Регион появляется в `/regions`, клавиатуре бота и валидации API
автоматически — из `config/regions.yaml`.
