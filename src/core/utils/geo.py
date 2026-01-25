"""
Geographic utility functions for coordinate calculations and transformations.

This module consolidates all geographic calculations used across the codebase:
- Haversine distance calculation (meters, feet, kilometers, miles)
- Coordinate Reference System (CRS) transformations
- Bounding box validation

Usage:
    from src.core.utils.geo import haversine_distance, transform_coordinates

    # Calculate distance in meters
    distance_m = haversine_distance(42.26, -71.80, 42.27, -71.81)

    # Calculate distance in feet
    distance_ft = haversine_distance(42.26, -71.80, 42.27, -71.81, unit='feet')

    # Transform MA State Plane to WGS84
    lat, lng = transform_coordinates(2893456.78, 987654.32, from_crs='EPSG:2249')
"""

import math
from typing import Tuple, Optional, Literal
from functools import lru_cache

# Earth radius constants
EARTH_RADIUS_METERS = 6_371_000
EARTH_RADIUS_FEET = 20_902_231
EARTH_RADIUS_KM = 6_371
EARTH_RADIUS_MILES = 3_958.8

# Unit type for type hints
DistanceUnit = Literal['meters', 'feet', 'kilometers', 'miles']


def haversine_distance(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    unit: DistanceUnit = 'meters'
) -> float:
    """
    Calculate the great-circle distance between two points on Earth.

    Uses the Haversine formula which gives accurate results for most distances.

    Args:
        lat1: Latitude of first point in decimal degrees
        lon1: Longitude of first point in decimal degrees
        lat2: Latitude of second point in decimal degrees
        lon2: Longitude of second point in decimal degrees
        unit: Unit for the result ('meters', 'feet', 'kilometers', 'miles')

    Returns:
        Distance between the two points in the specified unit

    Example:
        >>> haversine_distance(42.2626, -71.8023, 42.2700, -71.8100)
        1023.45  # meters
        >>> haversine_distance(42.2626, -71.8023, 42.2700, -71.8100, unit='feet')
        3357.12  # feet
    """
    # Select earth radius based on unit
    earth_radius = {
        'meters': EARTH_RADIUS_METERS,
        'feet': EARTH_RADIUS_FEET,
        'kilometers': EARTH_RADIUS_KM,
        'miles': EARTH_RADIUS_MILES,
    }.get(unit, EARTH_RADIUS_METERS)

    # Convert to radians
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    # Haversine formula
    a = (
        math.sin(delta_phi / 2) ** 2 +
        math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return earth_radius * c


@lru_cache(maxsize=4)
def get_crs_transformer(
    from_crs: str = "EPSG:2249",
    to_crs: str = "EPSG:4326"
) -> "Transformer":
    """
    Get a cached CRS transformer for coordinate transformations.

    Common CRS codes:
    - EPSG:2249: MA State Plane NAD83 (feet) - used in Worcester Address_Points
    - EPSG:4326: WGS84 (lat/lng) - standard GPS coordinates
    - EPSG:3857: Web Mercator - used by web maps

    Args:
        from_crs: Source coordinate reference system
        to_crs: Target coordinate reference system

    Returns:
        pyproj Transformer instance (cached)

    Raises:
        ImportError: If pyproj is not installed
    """
    try:
        from pyproj import Transformer
    except ImportError:
        raise ImportError(
            "pyproj package required for CRS transformations. "
            "Install with: pip install pyproj"
        )

    return Transformer.from_crs(from_crs, to_crs, always_xy=True)


def transform_coordinates(
    x: float,
    y: float,
    from_crs: str = "EPSG:2249",
    to_crs: str = "EPSG:4326"
) -> Tuple[float, float]:
    """
    Transform coordinates between coordinate reference systems.

    Args:
        x: X coordinate (easting/longitude)
        y: Y coordinate (northing/latitude)
        from_crs: Source CRS (default: MA State Plane)
        to_crs: Target CRS (default: WGS84)

    Returns:
        Tuple of (longitude, latitude) if to_crs is EPSG:4326,
        or (x, y) in target CRS

    Example:
        # Convert MA State Plane feet to lat/lng
        >>> lng, lat = transform_coordinates(2893456.78, 987654.32)
        >>> print(f"Lat: {lat}, Lng: {lng}")
        Lat: 42.2626, Lng: -71.8023
    """
    transformer = get_crs_transformer(from_crs, to_crs)
    return transformer.transform(x, y)


def is_within_bounds(
    lat: float,
    lng: float,
    bounds: Optional[dict] = None
) -> bool:
    """
    Check if coordinates are within a bounding box.

    Args:
        lat: Latitude to check
        lng: Longitude to check
        bounds: Dictionary with min_lat, max_lat, min_lng, max_lng
                If None, uses Worcester MA bounds

    Returns:
        True if coordinates are within bounds

    Example:
        >>> is_within_bounds(42.26, -71.80)  # Worcester
        True
        >>> is_within_bounds(40.71, -74.01)  # NYC
        False
    """
    # Default Worcester bounds
    if bounds is None:
        bounds = {
            "min_lat": 42.20,
            "max_lat": 42.35,
            "min_lng": -71.90,
            "max_lng": -71.70,
        }

    return (
        bounds["min_lat"] <= lat <= bounds["max_lat"] and
        bounds["min_lng"] <= lng <= bounds["max_lng"]
    )


def calculate_bounding_box(
    lat: float,
    lng: float,
    radius_meters: float
) -> dict:
    """
    Calculate a bounding box around a point.

    Args:
        lat: Center latitude
        lng: Center longitude
        radius_meters: Radius in meters

    Returns:
        Dictionary with min_lat, max_lat, min_lng, max_lng
    """
    # Approximate degrees per meter at this latitude
    lat_per_meter = 1 / 111_320
    lng_per_meter = 1 / (111_320 * math.cos(math.radians(lat)))

    lat_delta = radius_meters * lat_per_meter
    lng_delta = radius_meters * lng_per_meter

    return {
        "min_lat": lat - lat_delta,
        "max_lat": lat + lat_delta,
        "min_lng": lng - lng_delta,
        "max_lng": lng + lng_delta,
    }
