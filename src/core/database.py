"""
Centralized database client factory for Supabase.

Provides a single point of initialization for Supabase clients across the codebase.
Handles connection validation and error handling consistently.

Usage:
    from src.core.database import get_supabase_client

    # Get a Supabase client (singleton)
    client = get_supabase_client()

    # Query data
    result = client.table('worcester_data_collection').select('*').execute()
"""

import logging
from typing import Optional
from functools import lru_cache

from src.core.config import settings

logger = logging.getLogger(__name__)

# Lazy import to avoid import errors when supabase is not installed
_supabase_client: Optional["Client"] = None


class SupabaseClientError(Exception):
    """Raised when Supabase client cannot be created."""
    pass


@lru_cache(maxsize=1)
def get_supabase_client(
    url: Optional[str] = None,
    key: Optional[str] = None,
    raise_on_error: bool = True
) -> Optional["Client"]:
    """
    Get a Supabase client instance (singleton).

    Args:
        url: Override Supabase URL (uses settings.SUPABASE_URL by default)
        key: Override Supabase key (uses settings.SUPABASE_KEY by default)
        raise_on_error: If True, raises SupabaseClientError on failure.
                       If False, returns None on failure.

    Returns:
        Supabase Client instance or None if raise_on_error is False

    Raises:
        SupabaseClientError: If credentials are missing and raise_on_error is True
    """
    try:
        from supabase import create_client, Client
    except ImportError:
        msg = "supabase package not installed. Run: pip install supabase"
        logger.error(msg)
        if raise_on_error:
            raise SupabaseClientError(msg)
        return None

    # Use provided values or fall back to settings
    supabase_url = url or settings.SUPABASE_URL
    supabase_key = key or settings.SUPABASE_KEY

    if not supabase_url or not supabase_key:
        msg = (
            "Supabase credentials not configured. "
            "Set SUPABASE_URL and SUPABASE_KEY environment variables."
        )
        logger.warning(msg)
        if raise_on_error:
            raise SupabaseClientError(msg)
        return None

    try:
        client = create_client(supabase_url, supabase_key)
        logger.debug("Supabase client created successfully")
        return client
    except Exception as e:
        msg = f"Failed to create Supabase client: {e}"
        logger.error(msg)
        if raise_on_error:
            raise SupabaseClientError(msg) from e
        return None


def clear_client_cache():
    """Clear the cached Supabase client (useful for testing)."""
    get_supabase_client.cache_clear()


# Table name constants
class Tables:
    """Supabase table names used in the project."""
    WORCESTER_DATA = "worcester_data_collection"


# Common query helpers
def fetch_properties_paginated(
    client: "Client",
    columns: str = "*",
    filters: Optional[dict] = None,
    batch_size: int = 1000,
    order_by: Optional[str] = None
):
    """
    Generator that yields properties in batches from Supabase.

    Args:
        client: Supabase client instance
        columns: Columns to select (default: all)
        filters: Dictionary of filters to apply
        batch_size: Number of records per batch
        order_by: Column to order by

    Yields:
        Lists of property records
    """
    offset = 0

    while True:
        query = client.table(Tables.WORCESTER_DATA).select(columns)

        # Apply filters
        if filters:
            for key, value in filters.items():
                if value is None:
                    query = query.is_(key, "null")
                else:
                    query = query.eq(key, value)

        # Apply ordering
        if order_by:
            query = query.order(order_by)

        # Apply pagination
        query = query.range(offset, offset + batch_size - 1)

        result = query.execute()

        if not result.data:
            break

        yield result.data

        if len(result.data) < batch_size:
            break

        offset += batch_size
