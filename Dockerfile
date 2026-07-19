# Отдельный образ специально для Bothost: платформа деплоит один Dockerfile
# из корня репозитория и не понимает docker-compose, поэтому здесь нельзя
# просто взять Dockerfile.api/Dockerfile.bot из локальной сборки — Bothost их
# не найдёт. Вместо этого один и тот же образ используется для ДВУХ ботов в
# панели Bothost (api и telegram-bot), а какой процесс запускать внутри —
# решает переменная окружения SERVICE_ROLE (см. entrypoint.sh и README).
#
# Для локальной разработки и docker-compose используй Dockerfile.api /
# Dockerfile.bot — этот файл существует только ради Bothost.
FROM python:3.11-slim

WORKDIR /srv/app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

# скачиваем веса эмбеддера на этапе сборки — иначе первый запрос на Bothost
# тянет модель с HuggingFace под прокси и часто заканчивается 502
RUN python -c "from sentence_transformers import SentenceTransformer; \
SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"

COPY app ./app
COPY data ./data
COPY migrations ./migrations
COPY alembic.ini .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh && mkdir -p /app/data

EXPOSE 8000

CMD ["./entrypoint.sh"]
