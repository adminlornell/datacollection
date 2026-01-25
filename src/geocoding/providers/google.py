"""
Google Geocoding API provider.

Paid, accurate geocoding service with caching support.
https://developers.google.com/maps/documentation/geocoding
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime

import requests

from src.core import settings
from src.core.utils.geo import is_within_bounds
from src.geocoding.base import BaseGeocoder, GeocodingResult, GeocodingError

logger = logging.getLogger(__name__)

GOOGLE_GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"


class GoogleGeocoder(BaseGeocoder):
    """
    Google Geocoding API provider.

    Pros:
    - Very accurate
    - Global coverage
    - Good address normalization

    Cons:
    - Requires API key
    - Paid service (~$5 per 1000 requests)

    Usage:
        geocoder = GoogleGeocoder()  # Uses GOOGLE_GEOCODING_API_KEY from env
        result = await geocoder.geocode("360 Plantation St")

    Caching:
        Results are cached to data/geocoding_cache.json to reduce API costs.
    """

    def __init__(self, api_key: Optional[str] = None, use_cache: bool = True):
        """
        Initialize Google Geocoder.

        Args:
            api_key: Google API key (uses settings if not provided)
            use_cache: Whether to use file-based caching
        """
        self.api_key = api_key or settings.GOOGLE_GEOCODING_API_KEY
        self.use_cache = use_cache
        self._cache: Dict[str, dict] = {}

        if use_cache:
            self._load_cache()

    @property
    def provider_name(self) -> str:
        return "google"

    @property
    def rate_limit_delay(self) -> float:
        return settings.GOOGLE_GEOCODER_DELAY

    @property
    def cache_path(self) -> Path:
        return settings.GEOCODING_CACHE_PATH

    def _load_cache(self):
        """Load cache from file."""
        if self.cache_path.exists():
            try:
                with open(self.cache_path) as f:
                    self._cache = json.load(f)
                logger.debug(f"Loaded {len(self._cache)} cached geocoding results")
            except Exception as e:
                logger.warning(f"Failed to load geocoding cache: {e}")
                self._cache = {}

    def _save_cache(self):
        """Save cache to file."""
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_path, "w") as f:
                json.dump(self._cache, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save geocoding cache: {e}")

    def _cache_key(self, address: str) -> str:
        """Generate cache key from address."""
        return address.lower().strip()

    async def geocode(
        self,
        address: str,
        city: str = "Worcester",
        state: str = "MA",
        validate_bounds: bool = True,
        skip_cache: bool = False,
        **kwargs
    ) -> Optional[GeocodingResult]:
        """
        Geocode an address using Google Geocoding API.

        Args:
            address: Street address
            city: City name
            state: State code
            validate_bounds: If True, validate result is within Worcester bounds
            skip_cache: If True, bypass cache and make fresh API call

        Returns:
            GeocodingResult if successful
        """
        if not self.api_key:
            raise GeocodingError(
                "GOOGLE_GEOCODING_API_KEY not configured",
                provider=self.provider_name,
                address=address
            )

        # Format full address
        full_address = f"{address}, {city}, {state}"
        cache_key = self._cache_key(full_address)

        # Check cache
        if self.use_cache and not skip_cache and cache_key in self._cache:
            cached = self._cache[cache_key]
            logger.debug(f"Google: Cache hit for {address}")
            return GeocodingResult(
                latitude=cached["lat"],
                longitude=cached["lng"],
                matched_address=cached.get("formatted_address", ""),
                confidence=1.0 if cached.get("location_type") == "ROOFTOP" else 0.8,
                provider=self.provider_name,
                match_type=cached.get("location_type", "unknown"),
                geocoded_at=cached.get("geocoded_at", ""),
            )

        # Make API request
        params = {
            "address": full_address,
            "key": self.api_key,
        }

        try:
            response = requests.get(GOOGLE_GEOCODING_URL, params=params, timeout=10)
            data = response.json()

            if data.get("status") != "OK":
                if data.get("status") == "ZERO_RESULTS":
                    logger.debug(f"Google: No results for {address}")
                    return None
                elif data.get("status") == "OVER_QUERY_LIMIT":
                    raise GeocodingError(
                        "Google API quota exceeded",
                        provider=self.provider_name,
                        address=address
                    )
                else:
                    logger.warning(f"Google API error: {data.get('status')}")
                    return None

            # Get first result
            result = data["results"][0]
            location = result["geometry"]["location"]
            lat = location["lat"]
            lng = location["lng"]

            # Validate bounds
            if validate_bounds and not is_within_bounds(lat, lng):
                logger.warning(
                    f"Google: Coordinates outside Worcester for {address}: "
                    f"{lat}, {lng}"
                )
                return None

            # Cache result
            geocoded_at = datetime.utcnow().isoformat() + "Z"
            cache_entry = {
                "lat": lat,
                "lng": lng,
                "formatted_address": result.get("formatted_address", ""),
                "place_id": result.get("place_id", ""),
                "location_type": result.get("geometry", {}).get("location_type", ""),
                "geocoded_at": geocoded_at,
            }

            if self.use_cache:
                self._cache[cache_key] = cache_entry
                self._save_cache()

            return GeocodingResult(
                latitude=lat,
                longitude=lng,
                matched_address=result.get("formatted_address", ""),
                confidence=1.0 if cache_entry["location_type"] == "ROOFTOP" else 0.8,
                provider=self.provider_name,
                match_type=cache_entry["location_type"],
                raw_response=result,
                geocoded_at=geocoded_at,
            )

        except requests.Timeout:
            logger.warning(f"Google: Timeout for {address}")
            return None
        except Exception as e:
            logger.error(f"Google: Error geocoding {address}: {e}")
            return None

    def clear_cache(self):
        """Clear the geocoding cache."""
        self._cache = {}
        if self.cache_path.exists():
            self.cache_path.unlink()
        logger.info("Geocoding cache cleared")
