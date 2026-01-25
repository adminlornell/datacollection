"""
Shared utility functions for the Worcester data collection project.

Modules:
- geo: Geographic calculations (haversine, coordinate transforms, bounds checking)
- address: Address normalization and parsing
- formatting: Number, currency, and text formatting

Usage:
    from src.core.utils import haversine_distance, normalize_address, format_currency

    # Calculate distance
    distance = haversine_distance(42.26, -71.80, 42.27, -71.81, unit='meters')

    # Normalize address
    normalized = normalize_address("123 MAIN STREET, Worcester, MA 01610")

    # Format currency
    formatted = format_currency(1500000)  # "$1,500,000"
"""

from src.core.utils.geo import (
    haversine_distance,
    get_crs_transformer,
    transform_coordinates,
    is_within_bounds,
)
from src.core.utils.address import (
    normalize_address,
    parse_street_number,
    is_valid_address,
)
from src.core.utils.formatting import (
    format_currency,
    format_number,
    escape_html,
    format_status,
)

__all__ = [
    # Geo utilities
    "haversine_distance",
    "get_crs_transformer",
    "transform_coordinates",
    "is_within_bounds",
    # Address utilities
    "normalize_address",
    "parse_street_number",
    "is_valid_address",
    # Formatting utilities
    "format_currency",
    "format_number",
    "escape_html",
    "format_status",
]
