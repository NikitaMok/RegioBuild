from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import compare, feedback, info
from app.api.schemas import RegionInfo, RegionsResponse
from app.core.regions import REGIONS

app = FastAPI(
    title="RegioBuild API",
    description=(
        "Сравнение региональных строительных нормативов (РНГП/ТСН) для бизнеса: "
        "информационный режим и режим сравнения двух регионов."
    ),
    version="0.1.0",
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
