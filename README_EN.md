# RegioBuild

[Русская версия (основная)](README.md)

A reference service for comparing **regional urban-planning design standards
(RNGP/TSN)** of constituent entities of the Russian Federation against the
federal normative layer (SP 42.13330.2016, excerpts from Federal Law
No. 123-FZ of 22 July 2008, and sanitary rules and norms).

The core is an HTTP API and a LangGraph RAG agent: statements in the answer are
tied to a specific clause of a normative act, with regional and federal levels
kept distinct. The Telegram client is a demonstration UI; the same API can be
called from an external service.

Outputs are **reference material only**. They are not legal advice and do not
replace an opinion of counsel or a design organisation.

<p align="center">
  <img src="docs/screenshots/01-bot-about.png" alt="RegioBuild — Telegram overview" width="400"/>
</p>

---

## Purpose

Siting rules for capital-construction objects differ across Russian regions in
substance and document structure. Manual comparison of regional RNGP texts with
federal norms is time-consuming and prone to missing material clauses.

RegioBuild returns a clause-cited overview for an object type and one region
(or two regions in compare mode). It does not assess whether a particular plot
may be developed and does not cover municipal zoning (PZZ) outside the current
index.

Legal status (Russian): [`docs/LEGAL_DISCLAIMER.md`](docs/LEGAL_DISCLAIMER.md).

---

## Capabilities

- FastAPI: `/info`, `/compare`, `/api/v1/*`, `/health`, `/metrics`
- Telegram client (aiogram 3)
- PDF corpus: federal layer and RNGP for five regions; hierarchical clause parsing
- Hybrid retrieval (dense + BM25), citation grounding, numeric guardrail
- Explicit refusal when the corpus does not support a claim

<p align="center">
  <img src="docs/screenshots/02-bot-start.png" alt="Start: legal status" width="360"/>
  &nbsp;
  <img src="docs/screenshots/03-bot-rules.png" alt="Rules and disclaimer" width="360"/>
</p>

---

## Modes

1. **Single-region overview** — regional and federal requirements for a
   capital-construction object.
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
codes of practice or the full capital-construction object classifier.

---

## Stack

| Layer | Components |
|-------|------------|
| Language | Python 3.11 |
| Backend | FastAPI |
| Client | aiogram 3 |
| Orchestration | LangGraph |
| Embeddings | sentence-transformers (MiniLM; optional e5-large) |
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
Qdrant settings (`VECTOR_BACKEND=qdrant`). For local Chroma:
`pip install -r requirements-legacy-chroma.txt`.

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

## Author

Nikita Mokin / Никита Мокин

[GitHub](https://github.com/NikitaMok) · [LinkedIn](https://ru.linkedin.com/in/mokinnikita)

---

## Rights

© Nikita Mokin / Никита Мокин. **All rights reserved.**

Copying the repository, reproducing material parts of the solution, and
commercial use of the code or product **without prior written consent of the
rights holder are prohibited**. Publication on GitHub is for review and
demonstration of competence and does not grant a licence for commercial
exploitation.
