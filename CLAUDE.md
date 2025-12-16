# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Worcester MA property records scraper that collects data from gis.vgsi.com/worcesterma. Uses Playwright for browser automation with SQLite persistence via SQLAlchemy.

## Commands

```bash
# Setup
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Run full scraping pipeline
python main.py

# Run individual stages
python main.py --streets-only     # Stage 1: Scrape street list
python main.py --properties-only  # Stage 2: Scrape property listings
python main.py --details-only     # Stage 3: Scrape property details
python main.py --download-only    # Stage 4: Download photos/layouts

# Other operations
python main.py --status           # Check progress
python main.py --export           # Export to CSV/JSON
python main.py --no-resume        # Start fresh (ignore saved progress)
python main.py --details-only --limit 10  # Limit items for testing

# Scrape a single street (standalone utility)
python scrape_single_street.py "WACHUSETT ST" --limit 10
```

## Architecture

**4-Stage Pipeline** (main.py → `WorcesterPropertyScraper`):
1. `StreetScraper` - Extracts all street names/URLs from Streets.aspx
2. `PropertyScraper` - For each street, extracts property listings with parcel IDs
3. `PropertyDetailScraper` - Visits each property page for detailed info (owner, building, land, assessment)
4. `MediaDownloader` - Downloads property photos and layout sketches via aiohttp

**Scraper Hierarchy**:
- `BaseScraper` (src/scrapers/base_scraper.py) - Browser lifecycle, navigation with retry/backoff, helper methods
- All scrapers inherit from BaseScraper and use async context manager pattern (`async with Scraper(session)`)

**Data Models** (src/models.py):
- `Street` → `Property` (one-to-many)
- `Property` → `PropertyPhoto`, `PropertyLayout` (one-to-many)
- `ScrapingProgress` - Tracks resumability per task

**Configuration** (src/config.py, .env):
- `REQUEST_DELAY` - Seconds between requests (default 1.0)
- `HEADLESS` - Browser headless mode (default true)
- `MAX_CONCURRENT_DOWNLOADS` - Parallel download limit (default 5)
- Data stored in `worcester_properties.db` and `data/` directory

## Key Implementation Details

- All scrapers are async and use Playwright's async API
- Progress tracked in SQLite; interrupted runs resume automatically
- Rate limiting via configurable delays between requests
- Media downloads use aiohttp with semaphore for concurrency control
