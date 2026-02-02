"""Health check endpoint."""
from fastapi import APIRouter

from config import get_settings

router = APIRouter()


@router.get("/api/health")
async def health_check():
    """Health check endpoint."""
    settings = get_settings()
    return {
        "status": "ok",
        "version": settings.version,
    }
