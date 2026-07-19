from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from app.api.routes import compare, feedback, info
from app.api.schemas import RegionInfo, RegionsResponse
from app.core.regions import REGIONS
from app.embeddings.embedder import get_embedder
from app.vectorstore.chroma_store import get_chroma_store


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # на Bothost первый /compare иначе грузит модель под запросом и ловит 502
    # (прокси рвёт соединение / OOM). Прогреваем при старте — падение будет
    # видно в логах сразу, а не в середине диалога с пользователем.
    logger.info("прогрев embedder + chroma...")
    embedder = get_embedder()
    store = get_chroma_store()
    logger.info(f"embedder готов ({embedder.model_name}), векторов в chroma: {store.count()}")
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
