from __future__ import annotations

import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from app.api.routes import compare, feedback, info
from app.api.schemas import RegionInfo, RegionsResponse
from app.core.regions import REGIONS


def _warmup_models() -> None:
    try:
        from app.embeddings.embedder import get_embedder
        from app.vectorstore.chroma_store import get_chroma_store

        logger.info("прогрев embedder + chroma...")
        embedder = get_embedder()
        store = get_chroma_store()
        logger.info(f"embedder готов ({embedder.model_name}), векторов в chroma: {store.count()}")
    except Exception:
        logger.exception("прогрев embedder/chroma не удался — API всё равно слушает порт")


def _warmup_enabled() -> bool:
    return os.getenv("WARMUP_ON_START", "false").strip().lower() in {"1", "true", "yes"}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # На Bothost прогрев MiniLM при старте часто убивает контейнер по RAM (рестарт-цикл).
    # По умолчанию модель грузится лениво на первом /info|/compare.
    if _warmup_enabled():
        thread = threading.Thread(target=_warmup_models, name="warmup-embedder", daemon=True)
        thread.start()
    else:
        logger.info("прогрев при старте отключён (WARMUP_ON_START) — модель на первом запросе")
    yield


app = FastAPI(
    title="RegioBuild API",
    description=(
        "Сравнение региональных строительных нормативов (РНГП/ТСН) для бизнеса: "
        "информационный режим и режим сравнения двух регионов."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(info.router)
app.include_router(compare.router)
app.include_router(feedback.router)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/regions", response_model=RegionsResponse, tags=["system"])
def list_regions() -> RegionsResponse:
    return RegionsResponse(
        regions=[RegionInfo(code=region.code, display_name=region.display_name) for region in REGIONS.values()]
    )
