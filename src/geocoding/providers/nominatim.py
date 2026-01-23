"""
Nominatim (OpenStreetMap) Geocoder provider.

Free geocoding using OpenStreetMap data.
https://nominatim.org/
"""

import asyncio
import logging
from typing import Optional

import requests

from src.core import settings
from src.core.utils.geo import is_within_bounds
from src.geocoding.base import BaseGeocoder, GeocodingResult, GeocodingError

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


class NominatimGeocoder(BaseGeocoder):
    """
    Nominatim (OpenStreetMap) Geocoder.

    Pros:
    - Free
    - Good global coverage
    - Open data

    Cons:
    - Strict rate limiting (1 request/second)
    - Variable accuracy
    - Requires user agent

    Usage:
        geocoder = NominatimGeocoder()
        result = await geocoder.geocode("360 Plantation St")
    """

    def __init__(self, user_agent: str = "WorcesterPropertyEnricher/1.0"):
        """
        Initialize Nominatim Geocoder.

        Args:
            user_agent: User agent string (required by Nominatim TOS)
        """
        self.user_agent = user_agent

    @property
    def provider_name(self) -> str:
        return "nominatim"

    @property
    def rate_limit_delay(self) -> float:
        return settings.NOMINATIM_GEOCODER_DELAY

    async def geocode(
        self,
        address: str,
        city: str = "Worcester",
        state: str = "MA",
        validate_bounds: bool = True,
        **kwargs
    ) -> Optional[GeocodingResult]:
        """
        Geocode an address using Nominatim.

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
            "q": full_address,
            "format": "json",
            "addressdetails": 1,
            "limit": 1,
        }

        headers = {
            "User-Agent": self.user_agent,
            "Accept-Language": "en",
        }

        try:
            response = requests.get(
                NOMINATIM_URL,
                params=params,
                headers=headers,
                timeout=10
            )

            if response.status_code != 200:
                logger.warning(f"Nominatim HTTP {response.status_code} for {address}")
                return None

            data = response.json()

            if not data:
                logger.debug(f"Nominatim: No results for {address}")
                return None

            # Get first result
            result = data[0]
            lat = float(result["lat"])
            lng = float(result["lon"])

            # Validate bounds
            if validate_bounds and not is_within_bounds(lat, lng):
                logger.warning(
                    f"Nominatim: Coordinates outside Worcester for {address}: "
                    f"{lat}, {lng}"
                )
                return None

            # Calculate confidence based on type
            osm_type = result.get("type", "")
            if osm_type in ("house", "building"):
                confidence = 0.95
            elif osm_type in ("street", "road"):
                confidence = 0.7
            else:
                confidence = 0.5

            return GeocodingResult(
                latitude=lat,
                longitude=lng,
                matched_address=result.get("display_name", ""),
                confidence=confidence,
                provider=self.provider_name,
                match_type=osm_type,
                raw_response=result,
            )

        except requests.Timeout:
            logger.warning(f"Nominatim: Timeout for {address}")
            return None
        except Exception as e:
            logger.error(f"Nominatim: Error geocoding {address}: {e}")
            return None
