"""Health endpoint."""

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/health")
def health_check() -> dict[str, str]:
    """Return service health."""

    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }
