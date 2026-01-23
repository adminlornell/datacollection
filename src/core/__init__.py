"""
Core module providing shared configuration, database access, and utilities.

This module consolidates common functionality used across the codebase:
- Configuration management (settings, environment variables)
- Database client factory (Supabase)
- Utility functions (geo, address, formatting)

Usage:
    from src.core import settings, get_supabase_client
    from src.core.utils import haversine_distance, normalize_address, format_currency
"""

from src.core.config import settings, Settings
from src.core.database import get_supabase_client, SupabaseClientError

__all__ = [
    "settings",
    "Settings",
    "get_supabase_client",
    "SupabaseClientError",
]
