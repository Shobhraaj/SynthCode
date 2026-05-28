from fastapi import APIRouter, Depends

from backend.app.api.deps import settings_dep
from backend.app.config import Settings
from backend.app.models.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(settings_dep)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="synthcode-api",
        model_version=settings.MODEL_VERSION,
        inference_enabled=settings.INFERENCE_ENABLED,
    )

