# Общий образ для Bothost (платформа берёт только корневой Dockerfile).
# Роль процесса — SERVICE_ROLE=api|bot, см. entrypoint.sh.
# Embeddings: fastembed/ONNX (без PyTorch) — укладывается в лимит RAM контейнера.
FROM python:3.11-slim

WORKDIR /srv/app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    EMBEDDING_BACKEND=fastembed \
    DEPLOY_PROFILE=bothost-demo

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

# веса ONNX на этапе сборки — иначе первый запрос качает модель с HF
RUN python -c "from fastembed import TextEmbedding; \
TextEmbedding(model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"

COPY app ./app
COPY data ./data
COPY config ./config
COPY scripts ./scripts
COPY migrations ./migrations
COPY alembic.ini .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh && mkdir -p /app/data

# curated JSONL в образе; upsert в Chroma — только локально при установленном chromadb
RUN python -m scripts.ingest_curated

EXPOSE 8000

CMD ["./entrypoint.sh"]
