"""
FastAPI dependencies for the PropIntel AI API.

Provides dependency injection for database clients and services.
"""

import os
import sys
from typing import Optional

# Add parent directory to path for core module imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core import get_supabase_client, SupabaseClientError
from supabase import Client

# Cached Supabase client
_supabase_client: Optional[Client] = None


def get_supabase() -> Optional[Client]:
    """
    Get Supabase client as a FastAPI dependency.

    Usage:
        @app.get("/data")
        async def get_data(supabase: Client = Depends(get_supabase)):
            if supabase:
                return supabase.table("data").select("*").execute()
    """
    global _supabase_client

    if _supabase_client is None:
        try:
            _supabase_client = get_supabase_client(raise_on_error=False)
        except Exception:
            _supabase_client = None

    return _supabase_client


def require_supabase() -> Client:
    """
    Get Supabase client, raising an error if not configured.

    Usage:
        @app.post("/data")
        async def create_data(supabase: Client = Depends(require_supabase)):
            return supabase.table("data").insert({}).execute()
    """
    from fastapi import HTTPException

    client = get_supabase()
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Database not configured"
        )
    return client
