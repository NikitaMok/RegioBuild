# RegioBuild

[Русская версия (основная)](README.md)

**RegioBuild** is an API-first navigation service over regional urban-planning
design standards (RNGP/TSN) in the Russian Federation, read against the federal
normative layer. Given an object type and a region — or two regions for
comparison — it returns a structured overview tied to specific clauses, with
regional and federal levels kept distinct.

The core is an HTTP API and a retrieval agent (LangGraph): corpus search, answer
generation, and citation verification. The Telegram client is a demonstration
channel; external systems use the same endpoints.

<p align="center">
  <img src="docs/screenshots/01-bot-about.png" alt="RegioBuild — Telegram overview" width="400"/>
</p>

---

## Problem

In the United States, siting rules for construction differ materially across
states. A similar pattern exists across constituent entities of the Russian
Federation: regional RNGP/TSN texts diverge in substance and structure, and
manual alignment with federal norms is slow and prone to missing material
clauses.

The gap affects not only developers and investors, but anyone planning a
capital-construction object in a new region. RegioBuild addresses that need:
a fast, auditable overview of applicable corpus fragments with source citations.

Scope and limitations: [`docs/LEGAL_DISCLAIMER.md`](docs/LEGAL_DISCLAIMER.md)
(Russian).

---

## Capabilities

- FastAPI: `/info`, `/compare`, `/api/v1/*`, `/health`, `/metrics`
- Telegram client (aiogram 3)
- PDF corpus (federal layer and RNGP for five regions); hierarchical clause parsing
- Hybrid retrieval (dense + BM25), citation grounding, numeric guardrail
- Explicit refusal when the corpus does not support a claim

<p align="center">
  <img src="docs/screenshots/02-bot-start.png" alt="Bot start" width="360"/>
  &nbsp;
  <img src="docs/screenshots/03-bot-rules.png" alt="Rules and limitations" width="360"/>
</p>

---

## Modes

1. **Single-region overview** — regional and federal requirements for an object.
2. **Two-region comparison** — differences and overlaps with clause citations.

Clause numbers proposed by the model are checked against retrieved fragments;
unsupported numbers are omitted.

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
| `RU-FED` | Federal layer |

The index is limited to this corpus and does not claim full coverage of Russian
codes of practice or the full object classifier. Municipal zoning (PZZ) is out of
scope for the current index.

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
| Quality | pytest; Recall@k, MRR |
| Infrastructure | Docker, GitHub Actions, Prometheus, Sentry |

One Docker image; process role via `SERVICE_ROLE=api` or `bot`.

Architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).  
Deployment: [`docs/BOTHOST_CHECKLIST.md`](docs/BOTHOST_CHECKLIST.md).

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

Configure GigaChat credentials in `.env`, and optionally the bot token and
Qdrant settings (`VECTOR_BACKEND=qdrant`, `EMBEDDING_BACKEND=fastembed`). For
local Chroma: `pip install -r requirements-legacy-chroma.txt`.

```bash
alembic upgrade head
python -m scripts.parse_pdf_docs   # if data/raw/docs is present
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

CI (GitHub Actions) runs a light suite without torch. Post-deploy smoke:
`python -m scripts.smoke_wave1_prod --api-url https://…`.

---

© Nikita Mokin / Никита Мокин.  
[GitHub](https://github.com/NikitaMok) · [LinkedIn](https://ru.linkedin.com/in/mokinnikita)

All rights reserved. Copying the repository, reproducing material parts of the
solution, and commercial use of the code or product without prior written
consent of the rights holder are prohibited. Publication on GitHub is for review
and demonstration of competence and does not grant a licence for commercial
exploitation.
