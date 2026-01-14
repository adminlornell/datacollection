"""
Configuration settings for the Worcester MA property scraper.
"""
import os
from pathlib import Path

# Base URLs
BASE_URL = "https://gis.vgsi.com/worcesterma"
STREETS_URL = f"{BASE_URL}/Streets.aspx"
PARCEL_URL = f"{BASE_URL}/Parcel.aspx"

# Database (SQLite - local)
DATABASE_PATH = os.getenv("DATABASE_PATH", "worcester_properties.db")

# Supabase Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://cxcgeumhfjvnuibxnbob.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")  # Set via environment variable

# Storage paths
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
PHOTOS_DIR = DATA_DIR / "photos"
LAYOUTS_DIR = DATA_DIR / "layouts"
EXPORTS_DIR = DATA_DIR / "exports"

# Create directories
for dir_path in [DATA_DIR, PHOTOS_DIR, LAYOUTS_DIR, EXPORTS_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# Scraping settings
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "1.0"))  # Seconds between requests
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
TIMEOUT = int(os.getenv("TIMEOUT", "30000"))  # Milliseconds

# Browser settings
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
SLOW_MO = int(os.getenv("SLOW_MO", "100"))  # Milliseconds delay between actions

# Concurrency
MAX_CONCURRENT_DOWNLOADS = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "5"))

# User agent (mimic real browser)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
