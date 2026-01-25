"""
US Census Bureau Geocoder provider.

Free, unlimited geocoding service optimized for US addresses.
https://geocoding.geo.census.gov/geocoder/
"""

import asyncio
import logging
from typing import Optional

import aiohttp

from src.core import settings
from src.core.utils.geo import is_within_bounds
from src.geocoding.base import BaseGeocoder, GeocodingResult, GeocodingError

logger = logging.getLogger(__name__)

CENSUS_GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
CENSUS_BATCH_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"


class CensusGeocoder(BaseGeocoder):
    """
    US Census Bureau Geocoder.

    Pros:
    - Free and unlimited
    - Good accuracy for US addresses
    - No API key required

    Cons:
    - US only
    - Rate limiting recommended (0.5s delay)
    - Can be slow during peak hours

    Usage:
        geocoder = CensusGeocoder()
        result = await geocoder.geocode("360 Plantation St")
    """

    @property
    def provider_name(self) -> str:
        return "census"

    @property
    def rate_limit_delay(self) -> float:
        return settings.CENSUS_GEOCODER_DELAY

    async def geocode(
        self,
        address: str,
        city: str = "Worcester",
        state: str = "MA",
        validate_bounds: bool = True,
        **kwargs
    ) -> Optional[GeocodingResult]:
        """
        Geocode an address using US Census Geocoder.

        Args:
            address: Street address
            city: City name
            state: State code
            validate_bounds: If True, validate result is within Worcester bounds

        Returns:
            GeocodingResult if successful
        """
        # Format full address
        full_address = f"{address}, {city}, {state}"

        params = {
            "address": full_address,
            "benchmark": "Public_AR_Current",
            "format": "json"
        }

        try:
            connector = aiohttp.TCPConnector(limit=5)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(
                    CENSUS_GEOCODER_URL,
                    params=params,
                    timeout=30
                ) as response:
                    if response.status != 200:
                        logger.warning(f"Census API HTTP {response.status} for {address}")
                        return None

                    data = await response.json()

                    # Check for matches
                    matches = data.get("result", {}).get("addressMatches", [])
                    if not matches:
                        logger.debug(f"Census: No match for {address}")
                        return None

                    # Get best match (first result)
                    match = matches[0]
                    coords = match.get("coordinates", {})
                    lat = coords.get("y")
                    lng = coords.get("x")

                    if not lat or not lng:
                        return None

                    # Validate bounds
                    if validate_bounds and not is_within_bounds(lat, lng):
                        logger.warning(
                            f"Census: Coordinates outside Worcester for {address}: "
                            f"{lat}, {lng}"
                        )
                        return None

                    return GeocodingResult(
                        latitude=lat,
                        longitude=lng,
                        matched_address=match.get("matchedAddress", ""),
                        confidence=1.0 if match.get("tigerLine") else 0.8,
                        provider=self.provider_name,
                        match_type=match.get("tigerLine", {}).get("side", "unknown"),
                        raw_response=match,
                    )

        except asyncio.TimeoutError:
            logger.warning(f"Census: Timeout for {address}")
            return None
        except Exception as e:
            logger.error(f"Census: Error geocoding {address}: {e}")
            return None

    async def batch_geocode_file(
        self,
        addresses: list,
        concurrency: int = 5
    ) -> dict:
        """
        Batch geocode using the Census batch API.

        Note: The batch API requires a specific CSV format.
        This method uses the individual API with concurrency for simplicity.
        """
        # Use parent's batch implementation with rate limiting
        return await self.batch_geocode(
            [{"id": a.get("parcel_id", str(i)), "address": a.get("location", a.get("address"))}
             for i, a in enumerate(addresses)],
            concurrency=concurrency
        )
