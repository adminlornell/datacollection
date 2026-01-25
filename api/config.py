"""
API configuration module.

Centralizes all configuration for the PropIntel AI API.
"""

import os
import sys

# Add parent directory to path for core module imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core import settings as core_settings


class APISettings:
    """API-specific settings extending core settings."""

    # Re-export core settings
    SUPABASE_URL = core_settings.SUPABASE_URL
    SUPABASE_KEY = core_settings.SUPABASE_KEY
    GEMINI_API_KEY = core_settings.GEMINI_API_KEY

    # API-specific settings
    API_TITLE = "PropIntel AI API"
    API_DESCRIPTION = "AI-powered commercial real estate analysis"
    API_VERSION = "1.0.0"

    # CORS settings
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
    CORS_ALLOW_CREDENTIALS = True
    CORS_ALLOW_METHODS = ["*"]
    CORS_ALLOW_HEADERS = ["*"]

    # Rate limiting (future use)
    RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))
    RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))

    @classmethod
    def validate_gemini(cls) -> bool:
        """Check if Gemini API key is configured."""
        return core_settings.validate_gemini()

    @classmethod
    def validate_supabase(cls) -> bool:
        """Check if Supabase is configured."""
        return core_settings.validate_supabase()


settings = APISettings()
