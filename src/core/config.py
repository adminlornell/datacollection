"""
Centralized configuration management for the Worcester data collection project.

All configuration is loaded from environment variables with sensible defaults.
Use the `settings` singleton for accessing configuration values.

Usage:
    from src.core.config import settings

    # Access configuration
    print(settings.SUPABASE_URL)
    print(settings.REQUEST_DELAY)
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
# Search in common locations
_env_paths = [
    Path(__file__).parent.parent.parent.parent / ".env",  # /dataCollection/.env
    Path(__file__).parent.parent.parent.parent / "datacollection" / ".env",  # /datacollection/.env
    Path.cwd() / ".env",  # Current working directory
]

for env_path in _env_paths:
    if env_path.exists():
        load_dotenv(env_path)
        break


@dataclass
class Settings:
    """Application settings loaded from environment variables."""

    # ==========================================================================
    # Supabase Configuration
    # ==========================================================================
    SUPABASE_URL: str = field(
        default_factory=lambda: os.getenv(
            "SUPABASE_URL",
            "https://cxcgeumhfjvnuibxnbob.supabase.co"
        )
    )
    SUPABASE_KEY: str = field(
        default_factory=lambda: os.getenv("SUPABASE_KEY", "")
    )

    # ==========================================================================
    # API Keys
    # ==========================================================================
    GOOGLE_GEOCODING_API_KEY: str = field(
        default_factory=lambda: os.getenv("GOOGLE_GEOCODING_API_KEY", "")
    )
    GEMINI_API_KEY: str = field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY", "")
    )

    # ==========================================================================
    # Scraper Base URLs
    # ==========================================================================
    BASE_URL: str = "https://gis.vgsi.com/worcesterma"

    @property
    def STREETS_URL(self) -> str:
        return f"{self.BASE_URL}/Streets.aspx"

    @property
    def PARCEL_URL(self) -> str:
        return f"{self.BASE_URL}/Parcel.aspx"

    # ==========================================================================
    # Database (Local SQLite)
    # ==========================================================================
    DATABASE_PATH: str = field(
        default_factory=lambda: os.getenv("DATABASE_PATH", "worcester_properties.db")
    )

    # ==========================================================================
    # Storage Paths
    # ==========================================================================
    DATA_DIR: Path = field(
        default_factory=lambda: Path(os.getenv("DATA_DIR", "data"))
    )

    @property
    def PHOTOS_DIR(self) -> Path:
        return self.DATA_DIR / "photos"

    @property
    def LAYOUTS_DIR(self) -> Path:
        return self.DATA_DIR / "layouts"

    @property
    def EXPORTS_DIR(self) -> Path:
        return self.DATA_DIR / "exports"

    @property
    def GEOCODING_CACHE_PATH(self) -> Path:
        return self.DATA_DIR / "geocoding_cache.json"

    # ==========================================================================
    # Scraping Settings
    # ==========================================================================
    REQUEST_DELAY: float = field(
        default_factory=lambda: float(os.getenv("REQUEST_DELAY", "1.0"))
    )
    MAX_RETRIES: int = field(
        default_factory=lambda: int(os.getenv("MAX_RETRIES", "3"))
    )
    TIMEOUT: int = field(
        default_factory=lambda: int(os.getenv("TIMEOUT", "30000"))
    )

    # ==========================================================================
    # Browser Settings
    # ==========================================================================
    HEADLESS: bool = field(
        default_factory=lambda: os.getenv("HEADLESS", "true").lower() == "true"
    )
    SLOW_MO: int = field(
        default_factory=lambda: int(os.getenv("SLOW_MO", "100"))
    )

    # ==========================================================================
    # Concurrency
    # ==========================================================================
    MAX_CONCURRENT_DOWNLOADS: int = field(
        default_factory=lambda: int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "5"))
    )

    # ==========================================================================
    # Rate Limiting (per provider)
    # ==========================================================================
    CENSUS_GEOCODER_DELAY: float = field(
        default_factory=lambda: float(os.getenv("CENSUS_GEOCODER_DELAY", "0.5"))
    )
    GOOGLE_GEOCODER_DELAY: float = field(
        default_factory=lambda: float(os.getenv("GOOGLE_GEOCODER_DELAY", "0.1"))
    )
    NOMINATIM_GEOCODER_DELAY: float = field(
        default_factory=lambda: float(os.getenv("NOMINATIM_GEOCODER_DELAY", "1.0"))
    )

    # ==========================================================================
    # Worcester MA Bounding Box (for coordinate validation)
    # ==========================================================================
    WORCESTER_BOUNDS: dict = field(default_factory=lambda: {
        "min_lat": 42.20,
        "max_lat": 42.35,
        "min_lng": -71.90,
        "max_lng": -71.70,
    })

    # ==========================================================================
    # User Agent
    # ==========================================================================
    USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def __post_init__(self):
        """Create required directories after initialization."""
        for dir_path in [self.DATA_DIR, self.PHOTOS_DIR, self.LAYOUTS_DIR, self.EXPORTS_DIR]:
            dir_path.mkdir(parents=True, exist_ok=True)

    def validate_supabase(self) -> bool:
        """Check if Supabase credentials are configured."""
        return bool(self.SUPABASE_URL and self.SUPABASE_KEY)

    def validate_google_geocoding(self) -> bool:
        """Check if Google Geocoding API key is configured."""
        return bool(self.GOOGLE_GEOCODING_API_KEY)

    def validate_gemini(self) -> bool:
        """Check if Gemini API key is configured."""
        return bool(self.GEMINI_API_KEY)

    def is_within_worcester_bounds(self, lat: float, lng: float) -> bool:
        """Check if coordinates are within Worcester MA bounding box."""
        bounds = self.WORCESTER_BOUNDS
        return (
            bounds["min_lat"] <= lat <= bounds["max_lat"] and
            bounds["min_lng"] <= lng <= bounds["max_lng"]
        )


# Singleton settings instance
settings = Settings()
