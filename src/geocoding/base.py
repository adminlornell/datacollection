"""
Base classes and interfaces for geocoding providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class GeocodingResult:
    """Standard result from any geocoding provider."""

    latitude: float
    longitude: float
    matched_address: str = ""
    confidence: float = 1.0  # 0.0 to 1.0
    provider: str = ""
    match_type: str = ""  # e.g., "rooftop", "range_interpolated"
    raw_response: Optional[Dict[str, Any]] = None
    geocoded_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    @property
    def as_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "matched_address": self.matched_address,
            "confidence": self.confidence,
            "provider": self.provider,
            "match_type": self.match_type,
            "geocoded_at": self.geocoded_at,
        }


class GeocodingError(Exception):
    """Exception raised when geocoding fails."""

    def __init__(self, message: str, provider: str = "", address: str = ""):
        self.message = message
        self.provider = provider
        self.address = address
        super().__init__(f"[{provider}] {message}" if provider else message)


class BaseGeocoder(ABC):
    """
    Abstract base class for geocoding providers.

    Subclasses must implement:
    - geocode(): Geocode a single address
    - provider_name: Name of the provider

    Optional overrides:
    - batch_geocode(): Geocode multiple addresses
    - validate_result(): Provider-specific validation
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the geocoding provider."""
        pass

    @property
    def rate_limit_delay(self) -> float:
        """Delay between requests in seconds."""
        return 1.0

    @abstractmethod
    async def geocode(
        self,
        address: str,
        city: str = "Worcester",
        state: str = "MA",
        **kwargs
    ) -> Optional[GeocodingResult]:
        """
        Geocode a single address.

        Args:
            address: Street address to geocode
            city: City name (default: Worcester)
            state: State code (default: MA)
            **kwargs: Provider-specific options

        Returns:
            GeocodingResult if successful, None if not found
        """
        pass

    async def batch_geocode(
        self,
        addresses: List[Dict[str, str]],
        concurrency: int = 5,
        **kwargs
    ) -> Dict[str, Optional[GeocodingResult]]:
        """
        Geocode multiple addresses.

        Default implementation calls geocode() sequentially.
        Providers can override for batch API support.

        Args:
            addresses: List of dicts with 'id' and 'address' keys
            concurrency: Max concurrent requests
            **kwargs: Provider-specific options

        Returns:
            Dict mapping id to GeocodingResult or None
        """
        import asyncio

        results = {}
        semaphore = asyncio.Semaphore(concurrency)

        async def geocode_one(item):
            async with semaphore:
                await asyncio.sleep(self.rate_limit_delay)
                result = await self.geocode(
                    item['address'],
                    city=item.get('city', 'Worcester'),
                    state=item.get('state', 'MA'),
                    **kwargs
                )
                return item['id'], result

        tasks = [geocode_one(addr) for addr in addresses]

        for coro in asyncio.as_completed(tasks):
            addr_id, result = await coro
            results[addr_id] = result

        return results

    def validate_result(
        self,
        result: GeocodingResult,
        bounds: Optional[dict] = None
    ) -> bool:
        """
        Validate a geocoding result.

        Args:
            result: GeocodingResult to validate
            bounds: Optional bounding box dict with min_lat, max_lat, min_lng, max_lng

        Returns:
            True if result is valid
        """
        from src.core.utils.geo import is_within_bounds

        # Check bounds if provided
        if bounds:
            return is_within_bounds(result.latitude, result.longitude, bounds)

        # Default: use Worcester bounds
        return is_within_bounds(result.latitude, result.longitude)
