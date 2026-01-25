"""
Geocoding facade providing a simple interface to all providers.
"""

import logging
from typing import Optional, List, Dict, Literal

from src.geocoding.base import GeocodingResult, GeocodingError, BaseGeocoder
from src.geocoding.providers.census import CensusGeocoder
from src.geocoding.providers.google import GoogleGeocoder
from src.geocoding.providers.nominatim import NominatimGeocoder

logger = logging.getLogger(__name__)

ProviderType = Literal["census", "google", "nominatim", "auto"]


def get_geocoder(provider: ProviderType = "census") -> BaseGeocoder:
    """
    Get a geocoder instance by provider name.

    Args:
        provider: Provider name ("census", "google", "nominatim")

    Returns:
        Geocoder instance
    """
    providers = {
        "census": CensusGeocoder,
        "google": GoogleGeocoder,
        "nominatim": NominatimGeocoder,
    }

    if provider not in providers:
        raise ValueError(f"Unknown provider: {provider}. Choose from: {list(providers.keys())}")

    return providers[provider]()


async def geocode_address(
    address: str,
    city: str = "Worcester",
    state: str = "MA",
    provider: ProviderType = "census",
    fallback_providers: Optional[List[str]] = None,
    validate_bounds: bool = True,
    **kwargs
) -> Optional[GeocodingResult]:
    """
    Geocode a single address with optional fallback providers.

    Args:
        address: Street address to geocode
        city: City name (default: Worcester)
        state: State code (default: MA)
        provider: Primary provider to use
        fallback_providers: List of providers to try if primary fails
        validate_bounds: Validate result is within Worcester bounds
        **kwargs: Additional provider-specific options

    Returns:
        GeocodingResult if successful, None if all providers fail

    Example:
        result = await geocode_address(
            "360 Plantation St",
            provider="census",
            fallback_providers=["nominatim"]
        )
    """
    # Try primary provider
    geocoder = get_geocoder(provider)
    result = await geocoder.geocode(
        address=address,
        city=city,
        state=state,
        validate_bounds=validate_bounds,
        **kwargs
    )

    if result:
        return result

    # Try fallback providers
    if fallback_providers:
        for fallback in fallback_providers:
            if fallback == provider:
                continue

            logger.debug(f"Trying fallback provider: {fallback}")
            geocoder = get_geocoder(fallback)
            result = await geocoder.geocode(
                address=address,
                city=city,
                state=state,
                validate_bounds=validate_bounds,
                **kwargs
            )

            if result:
                return result

    return None


async def geocode_batch(
    addresses: List[Dict[str, str]],
    provider: ProviderType = "census",
    concurrency: int = 5,
    **kwargs
) -> Dict[str, Optional[GeocodingResult]]:
    """
    Geocode multiple addresses.

    Args:
        addresses: List of dicts with 'id' and 'address' keys
        provider: Geocoding provider to use
        concurrency: Max concurrent requests
        **kwargs: Additional provider-specific options

    Returns:
        Dict mapping id to GeocodingResult or None

    Example:
        results = await geocode_batch([
            {"id": "1", "address": "360 Plantation St"},
            {"id": "2", "address": "1 City Square"},
        ])
    """
    geocoder = get_geocoder(provider)
    return await geocoder.batch_geocode(addresses, concurrency=concurrency, **kwargs)


async def compare_providers(
    address: str,
    city: str = "Worcester",
    state: str = "MA",
    providers: Optional[List[str]] = None,
) -> Dict[str, Optional[GeocodingResult]]:
    """
    Compare geocoding results from multiple providers.

    Useful for validating accuracy or finding discrepancies.

    Args:
        address: Address to geocode
        city: City name
        state: State code
        providers: List of providers to compare (default: all)

    Returns:
        Dict mapping provider name to result
    """
    from src.core.utils.geo import haversine_distance
    import asyncio

    if providers is None:
        providers = ["census", "nominatim"]
        # Only add Google if API key is configured
        from src.core import settings
        if settings.validate_google_geocoding():
            providers.append("google")

    results = {}
    for provider in providers:
        geocoder = get_geocoder(provider)
        await asyncio.sleep(geocoder.rate_limit_delay)
        results[provider] = await geocoder.geocode(address, city, state)

    # Calculate distances between results
    valid_results = {k: v for k, v in results.items() if v is not None}
    if len(valid_results) > 1:
        provider_names = list(valid_results.keys())
        for i, p1 in enumerate(provider_names):
            for p2 in provider_names[i+1:]:
                r1, r2 = valid_results[p1], valid_results[p2]
                dist = haversine_distance(
                    r1.latitude, r1.longitude,
                    r2.latitude, r2.longitude
                )
                logger.info(f"Distance {p1} vs {p2}: {dist:.1f}m")

    return results
