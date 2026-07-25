# Adding a new region

[Русская версия](ADDING_REGION.md)

The architecture is config-driven: a new constituent entity of the Russian
Federation is added via data and configuration, without code changes. The
procedure below was validated on the five pilot regions.

Municipal land-use rules (PZZ), local NGP and other municipal acts are **not
indexed**. The corpus accepts regional RNGP/TSN (and, where needed, a regional
urban-planning statute) plus the federal layer `RU-FED`.

## 1. Source documents

Place the PDF of the regional act (RNGP/TSN) in `data/raw/docs/`. Requirements:

- a text layer is mandatory (there is no OCR pipeline);
- use the current official edition (docs.cntd.ru or the region’s official legal
  portal);
- do not place municipal or other local acts in this folder for indexing.

## 2. Configuration

`config/regions.yaml` — region block with an ISO code:

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

`config/documents.yaml` — document entries with `ingest: true`
(regional level — `regulatory_level: regional`).

If needed, refine retrieval axes and the object tier (`group1` — specialised
RNGP objects; `group2` — framework commercial objects) in
`config/object_categories.yaml`.

## 3. Parsing and validation

```bash
python -m scripts.parse_pdf_docs        # PDF → data/structured/ + chunks
python -m scripts.validate_data         # configs and curated aligned
python -m scripts.audit_corpus          # junk numbering share in chunks
```

Check `data/structured/_summary.json`: clause/chunk counts for the new region
should match document volume; tables should be lifted.

## 4. Curated anchors (optional, recommended)

If key tables (parking, SPZ) parse poorly from PDF, add 3–7 records to
`data/curated/*.jsonl` following existing samples (region, `section_number`,
text with exact values, `business_types`).

## 5. Indexing

```bash
# full reindex (embedding backend must match runtime!)
EMBEDDING_BACKEND=fastembed VECTOR_BACKEND=qdrant python -m scripts.index_qdrant

# or incremental without reset
python -m scripts.index_qdrant --no-reset
```

## 6. Quality evaluation

Add 3–5 cases for the new region to `data/eval/golden.jsonl`
(object type + expected clauses) and run:

```bash
python -m scripts.eval_golden
```

Threshold: retrieval hit rate ≥ 0.8. Below that — inspect parse quality
(`section_number`) and add curated anchors.

## 7. Production

Push → deploy to VPS (`docker-compose.prod.yml`, `scripts/deploy_remote.sh`) →
`scripts/verify_deploy.sh` (`verify OK`) → smoke request for the new region via
`/api/v1/info`.

The region appears in `/regions`, the bot keyboard and API validation
automatically from `config/regions.yaml`.
