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

The LLM sits behind a provider abstraction: GigaChat Pro in production;
YandexGPT is in the codebase with failover off by default — no agent rewrite
to switch.

### Production

FastAPI + aiogram 3 + Docker. One image; process role via `SERVICE_ROLE=api|bot`.
Vectors on Qdrant Cloud; embeddings on memory-tight hosts use ONNX (fastembed),
without PyTorch in the runtime. Disk LLM cache avoids paying twice for the same
request.

### Observability

A commercial contour needs visibility, not only answers:

- Prometheus metrics on `GET /metrics` (including
  `regiobuild_guardrail_blocks_total`, latency and HTTP errors via the
  instrumentator)
- Grafana Cloud: remote-write / scrape credentials in env; pipeline notes in
  [`docs/GRAFANA.md`](docs/GRAFANA.md)
- Sentry via `SENTRY_DSN`

Metrics and the dashboard contour are part of the product; connecting scrape or
Alloy remote write to the public Bothost API completes the Cloud ↔ runtime link.

### Quality

Recall@k and MRR for retrieval. Pytest in CI (light suite without torch).
Post-deploy smoke checks that the contour is alive.

Architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).  
Deployment: [`docs/BOTHOST_CHECKLIST.md`](docs/BOTHOST_CHECKLIST.md).

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

## Corpus coverage

| ISO 3166-2 | Entity |
|------------|--------|
| `RU-MOS` | Moscow Oblast |
| `RU-KDA` | Krasnodar Krai |
| `RU-SVE` | Sverdlovsk Oblast |
| `RU-NVS` | Novosibirsk Oblast |
| `RU-TA` | Republic of Tatarstan |
| `RU-FED` | Federal layer (SP 42, excerpts from 123-FZ / SanPiN) |

The index is limited to this corpus and does not claim full coverage of Russian
codes of practice or the full object classifier.

---

## Status

**Working prototype.** Full loop: ingestion → index → agent → API → Telegram.

**Done**

- citation grounding and numeric guardrail  
- hybrid retrieval, Qdrant, ISO regions  
- requirement-category classifier  
- Docker, CI, Prometheus metrics, Grafana Cloud contour, tests, smoke  
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
| LLM | GigaChat Pro |
| Data | SQLAlchemy, Alembic |
| Observability | Prometheus `/metrics`, Grafana Cloud, Sentry |
| Infrastructure | Docker, GitHub Actions |

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

Or `docker compose up --build`. Postgres: `docker-compose.postgres.yml`.

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
