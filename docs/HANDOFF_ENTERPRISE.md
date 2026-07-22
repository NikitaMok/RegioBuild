# HANDOFF RegioBuild — после реализации Waves 0–6 (код)

Дата: 2026-07-22  
План: `.cursor/plans/regiobuild_enterprise_*.plan.md` (не редактировать из чата)

## HEAD / дерево

Проверить локально: `git status`, `git log -1`. Коммиты не создавались (только по просьбе).

## Сделано в коде

### Wave 0–1
- ISO регионы + aliases: `config/regions.yaml`, `app/core/regions.py` (`resolve_region_code`)
- Манифест PDF: `config/documents.yaml` (17 PDF; municipal `ingest: false`)
- `app/core/documents.py`
- PDF hierarchical parser: `app/ingestion/pdf_parser.py`
- Пайплайн: `python -m scripts.parse_pdf_docs`
- Результат: `data/structured/` — **7352 clauses / 7667 chunks** (`_summary.json`)
- Тесты: `tests/test_pdf_parser.py`

### Wave 2 (код; runtime Qdrant — нужен Docker)
- `app/vectorstore/qdrant_store.py`, hybrid BM25+dense в `retriever.py`
- `scripts/index_qdrant.py`
- `qdrant-client` в requirements; compose profile `enterprise` + сервис `qdrant`
- e5 prefixes + enterprise model в `embedder.py` / Settings
- **На этой машине Docker не найден** — индекс в Qdrant не прогнан. Chroma legacy + aliases `$in` работают.

### Wave 3
- Граф: normalize → understand → query_transform → retrieve → classify → rerank → LLM → format/guardrail
- `app/agent/rerank.py`, `guardrail.py`, `config/object_categories.yaml`
- temperature default 0.0

### Wave 4 (скелет, без ваших файлов)
- `scripts/train_category_classifier.py` (ждёт `categories.xlsx`)
- `scripts/eval_golden.py` (ждёт `golden.json`)

### Wave 5–6
- `/api/v1/info`, `/api/v1/compare` + `regiobuild_guardrail_blocks_total`
- `docs/GRAFANA.md`, доп. в `BOTHOST_CHECKLIST.md`
- `.env.example`: VECTOR_BACKEND, Qdrant, Grafana, DEPLOY_PROFILE
- docker-compose profiles

## Активный корпус (ingest: true)

Федеральные: ГрК, СП 42, 123-ФЗ, СанПиН  
Региональные РНГП: RU-MOS, RU-KDA, RU-SVE, RU-NVS, RU-TA  
Региональные законы: РТ, НСО  
Муниципальные Новосибирска: **не индексировать**

## Следующие шаги (новый чат / локально)

1. Установить Docker → `docker compose --profile enterprise up -d qdrant`
2. `VECTOR_BACKEND=qdrant` → `python -m scripts.index_qdrant` (сначала MiniLM/`bothost-demo`; e5 — `DEPLOY_PROFILE=enterprise`)
3. Прислать `categories.xlsx` + `golden.json` → train + eval
4. Grafana Cloud credentials в `.env` → дашборд по `docs/GRAFANA.md`
5. Smoke Bothost после recreate API→health→bot

## Не делать

- municipal ingest
- Yandex failover
- README white-label / питч продажи
- коммит секретов (`bothost-*.env`, Grafana tokens)

## Проверки

```bash
pytest tests/test_pdf_parser.py tests/test_regions_config.py tests/test_enterprise_wave.py tests/test_api.py tests/test_agent_nodes.py -q
python -m scripts.parse_pdf_docs   # уже прогнано
```
