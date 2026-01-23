"""
PropIntel AI API - FastAPI Backend

Provides AI-powered property analysis using Gemini 2.5 Flash with Google Search grounding.
Caches results in Supabase for fast retrieval.

API Structure:
- /           - Health check
- /health     - Detailed health check
- /api/analysis/{parcel_id} - Get cached analysis
- /api/analyze - Generate new analysis
"""

import os
import sys

# Add parent directory to path for core module imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.routers import health_router, analysis_router

# Initialize FastAPI
app = FastAPI(
    title=settings.API_TITLE,
    description=settings.API_DESCRIPTION,
    version=settings.API_VERSION,
)

# Configure CORS for dashboard access
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

# Include routers
app.include_router(health_router)
app.include_router(analysis_router)


# Startup event
@app.on_event("startup")
async def startup_event():
    """Log startup information."""
    print(f"Starting {settings.API_TITLE} v{settings.API_VERSION}")
    print(f"  Supabase configured: {settings.validate_supabase()}")
    print(f"  Gemini configured: {settings.validate_gemini()}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
