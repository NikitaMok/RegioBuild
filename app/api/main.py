from __future__ import annotations

import os
import sys
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from app.api.routes import compare, feedback, info
from app.api.schemas import RegionInfo, RegionsResponse
from app.core.config import get_settings
from app.core.regions import REGIONS


def _configure_logging() -> None:
    settings = get_settings()
    logger.remove()
    if settings.log_json:
        logger.add(
            sys.stderr,
            level=settings.log_level.upper(),
            serialize=True,
        )
    else:
        logger.add(sys.stderr, level=settings.log_level.upper())


def _init_sentry() -> None:
    settings = get_settings()
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            integrations=[FastApiIntegration()],
            traces_sample_rate=0.1,
        )
        logger.info("Sentry инициализирован")
    except Exception:
        logger.exception("не удалось инициализировать Sentry")


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


def _warmup_mode() -> str:
    """off | delayed | immediate — см. lifespan."""
    raw = os.getenv("WARMUP_ON_START", "delayed").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return "off"
    if raw in {"1", "true", "yes", "immediate"}:
        return "immediate"
    return "delayed"


def _warmup_delay_sec() -> int:
    try:
        return max(0, int(os.getenv("WARMUP_DELAY_SEC", "25")))
    except ValueError:
        return 25


def _delayed_warmup() -> None:
    delay = _warmup_delay_sec()
    if delay:
        logger.info(f"отложенный прогрев через {delay} с...")
        time.sleep(delay)
    _warmup_models()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _configure_logging()
    _init_sentry()
    # immediate при старте на Bothost часто ловит OOM → рестарт-цикл.
    # delayed: сначала /health и прокси, через ~25 с модель уже в RAM до первого юзера.
    mode = _warmup_mode()
    if mode == "immediate":
        threading.Thread(target=_warmup_models, name="warmup-embedder", daemon=True).start()
    elif mode == "delayed":
        threading.Thread(target=_delayed_warmup, name="warmup-embedder-delayed", daemon=True).start()
    else:
        logger.info("прогрев отключён (WARMUP_ON_START=off) — модель на первом запросе")
    yield


app = FastAPI(
    title="RegioBuild API",
    description=(
        "Сравнение региональных строительных нормативов (РНГП/ТСН) для бизнеса: "
        "информационный режим и режим сравнения двух регионов. "
        "Справочный навигатор по НПА, не юридическая консультация."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

try:
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator(
        should_group_status_codes=True,
        excluded_handlers=["/health", "/metrics"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
except Exception:
    logger.warning("prometheus-fastapi-instrumentator недоступен — /metrics отключён")

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
