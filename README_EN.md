# RegioBuild

[Русская версия (основная)](README.md)

A service for comparing **regional urban-planning design standards (RNGP/TSN)**
of constituent entities of the Russian Federation against the federal layer
(SP 42.13330.2016, excerpts from Federal Law No. 123-FZ of 22 July 2008, and
sanitary rules and norms).

The core is an HTTP API and a LangGraph RAG agent: statements in the answer are
tied to a specific normative clause, with regional and federal levels kept
distinct. The Telegram client is a demonstration UI; the same API can be called
from an external service.

<p align="center">
  <img src="docs/screenshots/01-bot-about.png" alt="RegioBuild — Telegram overview" width="400"/>
</p>

---

## Problem

Siting rules for capital-construction objects vary widely across Russian
regions. Comparing regional RNGP texts with federal norms by hand is slow and
easy to get wrong on material clauses.

RegioBuild returns a **reference overview** for an object type and one region
(or two regions in compare mode), with clause numbers and regulation level.
It is not legal advice and not an opinion on whether a particular plot may be
developed.

---

## What is in the repo

- Telegram client (aiogram 3) and FastAPI (`/info`, `/compare`, `/api/v1/*`,
  `/health`, `/metrics`)
- PDF corpus (federal layer + RNGP for five regions), hierarchical clause
  parsing, hybrid retrieval (dense + BM25)
- Vector store: **Qdrant** (primary); Chroma kept as a local legacy option
- Citation grounding against retrieved fragments and a numeric guardrail
- Disclaimer and an explicit refusal when the corpus does not support a claim

This is a **working prototype**. Municipal zoning (PZZ) is out of scope for the
current index; coverage by object type and behaviour on rare phrasings are still
limited.

<p align="center">
  <img src="docs/screenshots/02-bot-start.png" alt="Start: legal status" width="360"/>
  &nbsp;
  <img src="docs/screenshots/03-bot-rules.png" alt="Rules and disclaimer" width="360"/>
</p>

Legal status (Russian): [`docs/LEGAL_DISCLAIMER.md`](docs/LEGAL_DISCLAIMER.md).

---

## Modes

1. **Single-region overview** — regional and federal requirements for a
   capital-construction object.
2. **Two-region comparison** — differences and overlaps with clause citations.

Clause numbers proposed by the model are checked against retrieved fragments.
Unsupported numbers are dropped.

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

Regions in the index: Moscow Oblast, Krasnodar Krai, Sverdlovsk Oblast,
Novosibirsk Oblast, Republic of Tatarstan (ISO 3166-2: `RU-MOS`, `RU-KDA`,
`RU-SVE`, `RU-NVS`, `RU-TA`). Federal layer: `RU-FED`.

Municipal Novosibirsk PDFs are listed in the manifest but **not ingested**;
they are reserved for a later stage.

The index does not claim full coverage of Russian codes of practice or the full
object classifier.

---

## Stack

| Layer | Components |
|-------|------------|
| Language | Python 3.11 |
| Backend | FastAPI |
| Client | aiogram 3 |
| Orchestration | LangGraph |
| Embeddings | sentence-transformers (multilingual MiniLM; optional e5-large) |
| Vector DB | Qdrant (primary), Chroma (legacy) |
| Classification | scikit-learn (TF-IDF + LogisticRegression) |
| LLM | GigaChat Pro (production); YandexGPT present in code, failover off by default |
| Data | SQLAlchemy, Alembic, disk LLM cache |
| Quality | pytest; Recall@k, MRR |
| Infrastructure | Docker, GitHub Actions, Prometheus, Sentry |

Single Docker image; process role via `SERVICE_ROLE=api|bot`.

Pipeline: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) (Russian).  
Deploy notes: [`docs/BOTHOST_CHECKLIST.md`](docs/BOTHOST_CHECKLIST.md) (Russian).

---

## Repository layout

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

---

## Local run

```bash
python -m venv venv
venv\Scripts\activate          # Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env         # Linux/Mac: cp .env.example .env
```

Put GigaChat credentials (and bot token if needed) in `.env`, plus Qdrant
settings (`VECTOR_BACKEND=qdrant`). For local Chroma:
`pip install -r requirements-legacy-chroma.txt`.

```bash
alembic upgrade head
python -m scripts.parse_pdf_docs
python -m scripts.index_qdrant

uvicorn app.api.main:app --reload
python -m app.bot.main
```

Or `docker compose up --build`. Postgres: `docker-compose.postgres.yml`.

---

## Tests

```bash
pytest
python -m app.eval.retrieval_eval
python -m app.eval.answer_eval
```

CI runs a reduced suite without torch. Post-deploy smoke:
`python -m scripts.smoke_wave1_prod --api-url https://…`.

---

## Author

Nikita Mokin

[GitHub](https://github.com/NikitaMok) · [LinkedIn](https://ru.linkedin.com/in/mokinnikita)

---

## Rights

© Nikita Mokin. **All rights reserved.**

Copying the repository, reproducing substantial parts of the solution, and
using the code or product commercially **without prior written consent of the
rights holder is prohibited**. Sources on GitHub are for review and portfolio
demonstration and do not grant a commercial licence.
