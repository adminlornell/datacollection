"""
Consolidated geocoding module for Worcester property data.

Provides a unified interface for multiple geocoding providers:
- Census: US Census Bureau Geocoder (free, unlimited)
- Google: Google Geocoding API (paid, accurate)
- Nominatim: OpenStreetMap (free, 1 req/sec limit)
- AddressPoints: City of Worcester official data

Usage:
    from src.geocoding import CensusGeocoder, GoogleGeocoder, geocode_address

    # Using specific provider
    geocoder = CensusGeocoder()
    result = await geocoder.geocode("360 Plantation St, Worcester, MA")

    # Using convenience function
    result = await geocode_address("360 Plantation St", provider="census")
"""

from src.geocoding.base import (
    GeocodingResult,
    GeocodingError,
    BaseGeocoder,
)
from src.geocoding.providers.census import CensusGeocoder
from src.geocoding.providers.google import GoogleGeocoder
from src.geocoding.providers.nominatim import NominatimGeocoder
from src.geocoding.facade import geocode_address, geocode_batch

__all__ = [
    # Base classes
    "GeocodingResult",
    "GeocodingError",
    "BaseGeocoder",
    # Providers
    "CensusGeocoder",
    "GoogleGeocoder",
    "NominatimGeocoder",
    # Convenience functions
    "geocode_address",
    "geocode_batch",
]
