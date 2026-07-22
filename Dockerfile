# Общий образ для Bothost (платформа берёт только корневой Dockerfile).
# Роль процесса — SERVICE_ROLE=api|bot, см. entrypoint.sh.
# Embeddings: fastembed/ONNX. PyTorch в образ не допускается.
FROM python:3.11-slim

WORKDIR /srv/app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    EMBEDDING_BACKEND=fastembed \
    DEPLOY_PROFILE=bothost-demo \
    WARMUP_ON_START=off \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt \
    && pip uninstall -y torch torchvision torchaudio sentence-transformers transformers 2>/dev/null || true \
    && python -c "import importlib.util as u; \
assert u.find_spec('torch') is None, 'torch must not be in Bothost image'; \
assert u.find_spec('sentence_transformers') is None, 'sentence_transformers must not be in Bothost image'"

# веса ONNX на этапе сборки — иначе первый запрос качает модель с HF
RUN python -c "from fastembed import TextEmbedding; \
TextEmbedding(model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', threads=1)"

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
