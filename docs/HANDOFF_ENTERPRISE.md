# HANDOFF RegioBuild — состояние после PDF-корпуса и Qdrant

Дата: 2026-07-22  
План enterprise в `.cursor/plans/` — не править из чата без нужды.

## HEAD

Проверять: `git status`, `git log -1`. Коммиты — только по просьбе.

## Сделано в коде

- ISO-регионы и алиасы: `config/regions.yaml`, `resolve_region_code`
- Манифест PDF: `config/documents.yaml` (municipal `ingest: false`)
- Hierarchical PDF parser → `data/structured` (~7352 clauses / 7667 chunks)
- Qdrant client, hybrid retrieve, rerank, guardrail, object categories
- Граф: normalize → understand → query_transform → retrieve → classify → rerank → LLM → format
- Скелеты `train_category_classifier.py`, `eval_golden.py` (ждут файлы автора)
- `/api/v1/info`, `/api/v1/compare`, метрика guardrail blocks
- `chromadb` вынесен в `requirements-legacy-chroma.txt` (сборка Bothost без него)

## Корпус

Федеральные: ГрК, СП 42, 123-ФЗ, СанПиН  
Региональные РНГП: RU-MOS, RU-KDA, RU-SVE, RU-NVS, RU-TA + законы РТ/НСО  
Муниципальные Новосибирска: не индексировать

## Не делать

- municipal ingest
- Yandex failover без явной просьбы
- white-label / питч в README
- коммит `.env`, `bothost-*.env`, токенов Grafana/Qdrant

## Дальше

1. Bothost: API с Qdrant env → `/health` → bot с новым `API_BASE_URL`
2. Стабильные grounded-ответы в Telegram
3. Grafana: scrape `/metrics` или Alloy remote write
4. При наличии `categories.xlsx` / `golden.json` — train + eval
