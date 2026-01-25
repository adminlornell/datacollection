"""
Health check endpoints.
"""

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "PropIntel AI API"}


@router.get("/health")
async def health():
    """Detailed health check."""
    from api.config import settings

    return {
        "status": "ok",
        "service": "PropIntel AI API",
        "version": settings.API_VERSION,
        "dependencies": {
            "supabase": settings.validate_supabase(),
            "gemini": settings.validate_gemini(),
        }
    }
