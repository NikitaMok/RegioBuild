# RegioBuild

[Русская версия (основная)](README.md)

Differences in regional urban-planning design standards across the Russian
Federation are a well-known problem that is almost impossible to close by hand.
Each constituent entity has its own requirements, act structure, and density of
regulation. Federal norms set a baseline, but regional specifics can change
everything.

I know this from legal practice. Manual comparison takes hours even for an
experienced lawyer — and when it feels complete, something material is often
still missing.

**RegioBuild** is an engineering answer to that problem.

<p align="center">
  <img src="docs/screenshots/01-bot-about.png" alt="RegioBuild — Telegram overview" width="400"/>
</p>

---

## What it is

A service for analysing regional urban-planning design standards (RNGP/TSN)
against the federal layer. Given an object type and a region — or two regions
for comparison — it returns a structured overview tied to normative clauses,
with regional and federal levels kept distinct.

Telegram is a demonstration channel at this stage. The core is an **HTTP API**
(`/info`, `/compare`, `/api/v1/*`, `/health`, `/metrics`) that external systems
can call independently of the messenger.

---

## How it works

### Ingestion

Regional acts arrive as PDF, HTML, DOCX, and noisy tables with false numbering.
A hierarchical parser extracts structured requirements; heuristics strip noise
before indexing. Skip that, and “clause 1” from a table caption lands in the
vector store — and retrieval feeds the model garbage.

Corpus manifest and ISO region codes live in `config/documents.yaml` and
`config/regions.yaml`. Municipal zoning (PZZ) is out of the current index.

### Retrieval

A user types “car wash”. The norms may say “car-wash bay”, “vehicle washing
facility”, or bury the rule in a table. Single-shot semantic search is not
enough.

The pipeline normalizes the object type, expands the query, and retrieves
hybrid-style: dense (Qdrant + fastembed/ONNX in production) plus BM25 over
candidates. Ranking prefers curated fragments and precise clause numbers. The
federal layer (`RU-FED`) is mixed in explicitly, without replacing the regional
act.

A TF-IDF + LogisticRegression classifier routes requirements into commercial
answer categories (holdout accuracy on the order of 88%).

### Grounding

The costliest failure mode in LegalTech is a confident invented clause number.
Here it is blocked in code: every clause the model proposes is checked against
retrieved fragments. No match — no clause in the answer. Empty retrieval —
explicit refusal, no fabricated norm. A numeric guardrail additionally checks
figures in the answer text.

### LangGraph agent

Nodes drive the flow end-to-end:

1. object-type normalization  
2. query understanding and mode (overview / compare)  
3. query transform  
4. retrieval  
5. requirement classification and rerank  
6. grounded generation and formatting  

The LLM sits behind a provider abstraction: **GigaChat Ultra** (`GigaChat-3-Ultra`
via `api.giga.chat`) in production; YandexGPT is in the codebase with failover
off by default — no agent rewrite to switch.

### Production

Production runs on an **Aeza VPS** (Moscow): nginx, API, Telegram bot,
Prometheus/Alertmanager, weekly backups. FastAPI + aiogram 3 + Docker; one image,
process role via `SERVICE_ROLE=api|bot`. Vectors on Qdrant Cloud; embeddings use
ONNX (fastembed), without PyTorch in the runtime. Disk LLM cache avoids paying
twice for the same request.

### Observability

A commercial contour needs visibility, not only answers:

- Prometheus metrics on `GET /metrics` (including
  `regiobuild_guardrail_blocks_total`, latency and HTTP errors via the
  instrumentator)
- Grafana Cloud: remote-write / scrape credentials in env; pipeline notes in
  [`docs/GRAFANA.md`](docs/GRAFANA.md)
- Sentry via `SENTRY_DSN`

Metrics and the dashboard contour are part of the product; connecting scrape or
Alloy remote write to the public API completes the Cloud ↔ runtime link.

Production on an Aeza VPS (nginx, backups, Prometheus/Alertmanager, SSH CI/CD):  
[`docs/PRODUCTION.md`](docs/PRODUCTION.md).

### Quality

Hit rate = share of cases where at least one expected `section_number` appears in
the agent's retrieval context (`python -m scripts.eval_golden`, retrieval mode).
This is **not** “legally correct answer” and not a building permit — only an
anchor-retrieval metric. Disclaimer: [`docs/LEGAL_DISCLAIMER.md`](docs/LEGAL_DISCLAIMER.md).

Targets: **100** cases in `data/eval/golden.jsonl`, hit rate **≥ 95%** (aim 99%).
`eval_golden` retrieval threshold: 0.95.

LLM: `temperature=0.0` on all calls (normalization, extraction, compare) for
deterministic NPA answers.

Current honest runs (`fastembed` + Qdrant, full corpus, no curated JSONL
force-inject and no CURATED-only search):

| Set | Hit rate | Role |
|-----|----------|------|
| `data/eval/golden.jsonl` | **100/100** | diagnostic anchors |
| `data/eval/blind_paraphrase.jsonl` | **60/60** | blind lawyer/builder paraphrases in pilot scope |

Blind ≥ 90% is the robustness target in scope; golden alone is not “ready for demo”.
Safety: citation grounding + numeric guardrail; weak/empty support → refusal.
Not claimed: site-level legal correctness of answers. Possible future commercial
upgrade: human-in-the-loop verification / deeper answer-eval (not current DoD).

Blind run:
`python -m scripts.eval_golden --golden data/eval/blind_paraphrase.jsonl`

Pytest in CI (light suite without torch). Post-deploy smoke checks that the
contour is alive.

Architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).  
Deployment: [`docs/PRODUCTION.md`](docs/PRODUCTION.md).

<p align="center">
  <img src="docs/screenshots/02-bot-start.png" alt="Bot start" width="360"/>
  &nbsp;
  <img src="docs/screenshots/03-bot-rules.png" alt="Usage limitations" width="360"/>
</p>

---

## Modes

1. **Single-region overview** — regional and federal requirements for an object.  
2. **Two-region comparison** — differences and overlaps with clause citations.

<p align="center">
  <img src="docs/screenshots/04-bot-modes.png" alt="Mode selection" width="360"/>
</p>

<p align="center">
  <img src="docs/screenshots/05-bot-info-avtomoika-kk.png" alt="Car wash in Krasnodar Krai" width="400"/>
</p>

<p align="center">
  <img src="docs/screenshots/06-bot-compare-sklad-rt-mo.png" alt="Warehouse compare: Tatarstan vs Moscow Oblast" width="400"/>
</p>

---

## Integration (API v1)

The commercial surface is `/api/v1` with `X-API-Key` authentication and a
machine-readable response: every requirement is tied to a clause, a regulatory
level (regional/federal) and the source-verification date. Interactive spec —
`GET /docs` (OpenAPI).

```bash
# issue a client key (server side)
python -m scripts.manage_api_keys create --name "Client LLC" --daily-limit 200

curl -X POST https://<host>/api/v1/info \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rgb_…" \
  -d '{"region": "RU-KDA", "object_type": "автомойка"}'
```

`/api/v1/compare` additionally returns `differences` (per-region values with
separate citations) and `common_requirements`. Client example —
[`examples/api_client.py`](examples/api_client.py).

Scaling to new regions is a data-and-config procedure, no code changes:
[`docs/ADDING_REGION.md`](docs/ADDING_REGION.md).

---

## Corpus coverage

| ISO 3166-2 | Entity |
|------------|--------|
| `RU-MOS` | Moscow Oblast |
| `RU-KDA` | Krasnodar Krai |
| `RU-SVE` | Sverdlovsk Oblast |
| `RU-NVS` | Novosibirsk Oblast |
| `RU-TA` | Republic of Tatarstan |
| `RU-FED` | Federal layer: Urban Planning Code, SP 42, 123-FZ, SanPiN (full PDF parse in index) |

The index is limited to this corpus and does not claim full coverage of all
Russian codes of practice or the full object classifier. Local zoning (PZZ) /
municipal level are out of scope.

---

## Status

**Working prototype.** Full loop: ingestion → index → agent → API → Telegram.

**Done**

- citation grounding and numeric guardrail  
- hybrid retrieval, Qdrant, ISO regions  
- requirement-category classifier  
- Docker, CI, Prometheus metrics, Grafana Cloud contour, tests, smoke  
- production on Aeza VPS (nginx, backups, monitoring)  
- API-first surface alongside the Telegram demo  

**Next**

- broader coverage (regions, municipal layer)  
- robustness on atypical phrasings  
- corpus refresh when norms change  
- lower answer latency (cache, profiling)  
- full scrape / remote write of metrics into Grafana Cloud in production  

---

## Stack

| Layer | Components |
|-------|------------|
| Language | Python 3.11 |
| Backend | FastAPI |
| Client | aiogram 3 |
| Orchestration | LangGraph |
| Embeddings | fastembed (ONNX); optional sentence-transformers |
| Vector DB | Qdrant (primary); Chroma as local legacy |
| Classification | scikit-learn (TF-IDF + LogisticRegression) |
| LLM | GigaChat Ultra (`GigaChat-3-Ultra`) |
| Data | SQLAlchemy, Alembic |
| Observability | Prometheus `/metrics`, Grafana Cloud, Sentry |
| Infrastructure | Docker, GitHub Actions, Aeza VPS |

---

## Repository and run

```
RegioBuild/
  app/           # agent, api, bot, ingestion, vectorstore, llm
  config/        # regions.yaml, documents.yaml, object_categories.yaml
  docs/
  migrations/
  scripts/
  tests/
  data/          # curated; raw/processed/structured — local
  Dockerfile
```

```bash
python -m venv venv
venv\Scripts\activate          # Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env         # Linux/Mac: cp .env.example .env
```

Configure GigaChat in `.env`, and optionally the bot token, Qdrant, and Grafana
Cloud settings. For local Chroma:
`pip install -r requirements-legacy-chroma.txt`.

```bash
alembic upgrade head
python -m scripts.parse_pdf_docs   # if data/raw/docs is present
python -m scripts.index_qdrant

uvicorn app.api.main:app --reload
python -m app.bot.main
```

Or `docker compose up --build`. Production VPS:
`docker compose -f docker-compose.prod.yml --env-file .env up -d --build`
(see [`docs/PRODUCTION.md`](docs/PRODUCTION.md)). Postgres: `docker-compose.postgres.yml`.

```bash
pytest
python -m app.eval.retrieval_eval
python -m app.eval.answer_eval
```

Post-deploy smoke: `python -m scripts.smoke_wave1_prod --api-url https://…`.

---

## Usage limitations

RegioBuild is a reference tool, not legal advice. Answers do not replace design
documentation, counsel’s opinion, or a check that norms are current at decision
time. Municipal PZZ acts are not in the index — verify them separately.

Details (Russian): [`docs/LEGAL_DISCLAIMER.md`](docs/LEGAL_DISCLAIMER.md).

---

© Nikita Mokin / Никита Мокин.  
[GitHub](https://github.com/NikitaMok) · [LinkedIn](https://ru.linkedin.com/in/mokinnikita)

All rights reserved. Copying the repository, reproducing material parts of the
solution, and commercial use of the code or product without prior written
consent of the rights holder are prohibited. Publication on GitHub is for review
and demonstration of competence and does not grant a licence for commercial
exploitation.
