# RegioBuild

[Русская версия (основная)](README.md)

**A project for comparing regional urban-planning design standards (RNGP/TSN)
of constituent entities of the Russian Federation**, taking into account
federal regulation (SP 42.13330.2016, excerpts from Federal Law No. 123-FZ of
22 July 2008, and sanitary rules and norms).

The Telegram client is a demonstration interface. The architectural core is a
FastAPI service and a RAG agent (LangGraph): material statements in the answer
are expected to be grounded in a specific normative clause. The API may be
deployed independently of the messenger.

<p align="center">
  <img src="docs/screenshots/01-bot-about.png" alt="RegioBuild — Telegram overview" width="400"/>
</p>

---

## Purpose

Legal regulation of capital-construction siting across Russian regions is
highly fragmented: the content and density of regional urban-planning design
standards differ substantially. Manual comparison of regional acts and federal
norms is labour-intensive and carries a real risk of omitting material
requirements.

RegioBuild produces a **reference overview** stating the clause number and the
level of regulation (regional / federal). The output does not replace legal
advice, design documentation, or a professional assessment of whether siting
is permissible.

---

## Current status

The repository includes a demonstration Telegram client, an HTTP API, a vector
index covering five constituent entities of the Russian Federation, and
programmatic verification of citations against retrieved corpus fragments. The
present build is a **working prototype**: broader subject coverage, municipal
zoning (PZZ), robustness on atypical query wording, and ongoing corpus
maintenance require further development — including by a team rather than a
single author.

Development and testing of the core (ingestion, index, agent, API, evaluation
runs) were carried out locally for an extended period. Publication of the
repository and connection of the Telegram client came later; the short public
git history primarily reflects deployment and the client layer, not the full
construction of the solution.

<p align="center">
  <img src="docs/screenshots/02-bot-start.png" alt="Start: legal status" width="360"/>
  &nbsp;
  <img src="docs/screenshots/03-bot-rules.png" alt="Rules and disclaimer" width="360"/>
</p>

**Legal status.** A reference navigator over fragments of normative legal acts;
it is **not** legal advice and **not** an opinion on whether an object may be
sited on a particular land plot. Municipal land-use and development rules and
other local acts may be absent from the index and must be verified separately.
Details: [`docs/LEGAL_DISCLAIMER.md`](docs/LEGAL_DISCLAIMER.md) (Russian).

---

## Capabilities

1. Overview of requirements for a capital-construction object in one
   constituent entity of the Russian Federation — with regional and federal
   levels separated.
2. Comparison of requirements between two entities — differences and overlaps
   with clause citations.

A clause number proposed by the language model is matched against fragments
retrieved from the index; where there is no verifiable support, the system
refrains from inventing a norm.

<p align="center">
  <img src="docs/screenshots/04-bot-modes.png" alt="Mode selection" width="360"/>
</p>

Example answers:

<p align="center">
  <img src="docs/screenshots/05-bot-info-avtomoika-kk.png" alt="Car wash in Krasnodar Krai" width="400"/>
</p>

<p align="center">
  <img src="docs/screenshots/06-bot-compare-sklad-rt-mo.png" alt="Warehouse compare: Tatarstan vs Moscow Oblast" width="400"/>
</p>

---

## Index coverage

Constituent entities currently represented in the index: Moscow Oblast,
Krasnodar Krai, Sverdlovsk Oblast, Novosibirsk Oblast, Republic of Tatarstan.

Federal layer: SP 42.13330.2016; curated fragments of Federal Law No. 123-FZ
and SanPiN for background comparison.

The index does not claim exhaustive coverage of the object classifier or the
full set of Russian codes of practice.

---

## Stack

| Layer | Components |
|-------|------------|
| Language | Python 3.11 |
| Backend | FastAPI (`/info`, `/compare`, `/health`, `/metrics`) |
| Client | aiogram 3 |
| Orchestration | LangGraph |
| Retrieval | sentence-transformers (multilingual MiniLM), Chroma |
| Classification | scikit-learn (TF-IDF + LogisticRegression) |
| LLM | GigaChat (production); YandexGPT also in code |
| Data | SQLAlchemy, Alembic, disk LLM response cache |
| Quality | pytest; Recall@k, MRR |
| Infrastructure | Docker, GitHub Actions, Prometheus, Sentry |

Single Docker image; process role via `SERVICE_ROLE=api|bot`.

Pipeline description: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) (Russian).

---

## Repository layout

```
RegioBuild/
  app/
    agent/         # LangGraph
    api/           # FastAPI
    bot/           # Telegram client
    classifier/
    core/
    db/
    embeddings/
    eval/
    ingestion/
    llm/
    vectorstore/
  config/          # regions.yaml
  docs/
  migrations/
  scripts/
  tests/
  data/
    curated/
    chroma/
    raw/ processed/  # local, not in git
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

LLM credentials and the bot token go in `.env`:

```bash
alembic upgrade head
python -m app.ingestion.pipeline
python -m app.embeddings.build_index
python -m app.classifier.train
python -m scripts.ingest_curated

uvicorn app.api.main:app --reload
python -m app.bot.main
```

Alternatively: `docker compose up --build`. Postgres variant:
`docker-compose.postgres.yml`. Deployment notes:
[`docs/BOTHOST_CHECKLIST.md`](docs/BOTHOST_CHECKLIST.md) (Russian).

---

## Testing

```bash
pytest
python -m app.eval.retrieval_eval
python -m app.eval.answer_eval
python -m scripts.audit_corpus
```

Continuous integration (GitHub Actions) runs a reduced suite without
torch/chroma. Post-deployment smoke: `scripts/smoke_wave1_prod.py`.

---

## Author

Nikita Mokin

[GitHub](https://github.com/NikitaMok) · [LinkedIn](https://ru.linkedin.com/in/mokinnikita)

---

## Rights

© Nikita Mokin. **All rights reserved.**

Copying the repository, reproducing substantial parts of the solution, and
using the code or product for commercial purposes **without the prior written
consent of the rights holder is prohibited**. Sources published on GitHub are
intended for review and demonstration of competence and do not constitute an
open-source licence for commercial exploitation.
