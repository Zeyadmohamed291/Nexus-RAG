import logging
from fastapi import APIRouter, Depends, status
from helpers.config import get_settings, Settings

logger = logging.getLogger("uvicorn.error")

base_router = APIRouter(
    prefix="/api/v1",
    tags=["Health & Info"],
)


@base_router.get("/", status_code=status.HTTP_200_OK)
async def welcome(app_settings: Settings = Depends(get_settings)):
    """Return application name, active version, and runtime status."""
    return {
        "app_name": app_settings.APP_NAME,
        "app_version": app_settings.APP_VERSION,
        "status": "healthy",
        "primary_language": app_settings.PRIMARY_LANG,
        "generation_backend": app_settings.GENERATION_BACKEND,
        "vector_backend": app_settings.VECTOR_DB_BACKEND,
    }
