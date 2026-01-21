#!/usr/bin/env python3
"""
Scrape missing parcels from Worcester MA GIS.

This script:
1. Reads the list of missing parcel IDs (account numbers)
2. Searches VGSI for each to get the PID
3. Scrapes the property details using the existing scraper
4. Saves to Supabase

Usage:
    python scrape_missing_parcels.py                    # Scrape all missing parcels
    python scrape_missing_parcels.py --limit 10        # Scrape first 10 for testing
    python scrape_missing_parcels.py --dry-run         # Just show what would be scraped
"""
import asyncio
import argparse
import os
import sys
import re
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.scrapers.supabase_scraper import SupabaseScraper
from src.config import SUPABASE_URL, SUPABASE_KEY

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('scrape_missing.log')
    ]
)
logger = logging.getLogger(__name__)

# Path to the missing parcels CSV
MISSING_PARCELS_CSV = "/Users/flyn/dataCollection/worcesterDataCollection/missing_parcels.csv"


async def search_parcel_by_acct(scraper: SupabaseScraper, acct_number: str) -> dict:
    """
    Search VGSI for a parcel by account number and return PID and details.

    Returns:
        dict with 'pid', 'address', 'owner' or None if not found
    """
    search_url = "https://gis.vgsi.com/worcesterma/Search.aspx"

    try:
        await scraper.navigate(search_url)
        await asyncio.sleep(0.5)

        # Select "Acct#" from dropdown
        await scraper.page.select_option("#MainContent_ddlSearchSource", "Acct#")
        await asyncio.sleep(0.3)

        # Enter account number and search
        await scraper.page.fill("#MainContent_txtSearchAcctNum", acct_number)
        await scraper.page.press("#MainContent_txtSearchAcctNum", "Enter")
        await asyncio.sleep(1)

        # Check for "No Data" message
        no_data = await scraper.page.query_selector("text=No Data for Current Search")
        if no_data:
            return None

        # Get first result link
        link = await scraper.page.query_selector("table#MainContent_grdSearchResults a[href*='Parcel.aspx']")
        if not link:
            return None

        href = await link.get_attribute("href")
        address = await link.inner_text()

        # Extract PID from href
        pid_match = re.search(r'pid=(\d+)', href, re.IGNORECASE)
        if not pid_match:
            return None

        pid = pid_match.group(1)

        # Try to get owner from table
        owner_cell = await scraper.page.query_selector("table#MainContent_grdSearchResults tr:nth-child(2) td:nth-child(2)")
        owner = await owner_cell.inner_text() if owner_cell else ""

        return {
            'pid': pid,
            'address': address.strip(),
            'owner': owner.strip(),
            'url': f"https://gis.vgsi.com/worcesterma/Parcel.aspx?pid={pid}"
        }

    except Exception as e:
        logger.error(f"Error searching for {acct_number}: {e}")
        return None


async def scrape_missing_parcels(limit: int = None, dry_run: bool = False):
    """Main function to scrape all missing parcels."""
    import pandas as pd

    # Load missing parcels
    if not os.path.exists(MISSING_PARCELS_CSV):
        logger.error(f"Missing parcels file not found: {MISSING_PARCELS_CSV}")
        logger.info("Run the comparison script first to generate this file.")
        return

    df = pd.read_csv(MISSING_PARCELS_CSV)
    total = len(df)

    if limit:
        df = df.head(limit)

    logger.info(f"Found {total} missing parcels, processing {len(df)}")

    if dry_run:
        logger.info("DRY RUN - showing first 20 parcels that would be scraped:")
        for i, row in df.head(20).iterrows():
            print(f"  {row['MAP_PAR_ID']:20} {row.get('ADDRESS', 'N/A')}")
        return

    # Initialize scraper
    scraper = SupabaseScraper()

    scraped = 0
    not_found = 0
    errors = 0

    async with scraper:
        for i, row in df.iterrows():
            acct_number = row['MAP_PAR_ID']
            address = row.get('ADDRESS', 'Unknown')

            logger.info(f"[{i+1}/{len(df)}] Searching for {acct_number} ({address})")

            try:
                # Search for parcel to get PID
                result = await search_parcel_by_acct(scraper, acct_number)

                if not result:
                    logger.warning(f"  Not found on VGSI: {acct_number}")
                    not_found += 1
                    continue

                logger.info(f"  Found PID {result['pid']}: {result['address']}")

                # Extract street name from address
                street_name = result['address'].split()[-2:] if result['address'] else "UNKNOWN"
                if isinstance(street_name, list):
                    street_name = " ".join(street_name)

                # Scrape property details
                await scraper.scrape_property_details(
                    parcel_id=result['pid'],
                    detail_url=result['url'],
                    street_name=street_name
                )

                scraped += 1
                logger.info(f"  Scraped successfully")

                # Rate limiting
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"  Error scraping {acct_number}: {e}")
                errors += 1
                continue

    # Summary
    logger.info("=" * 60)
    logger.info("SCRAPING COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Total processed: {len(df)}")
    logger.info(f"Successfully scraped: {scraped}")
    logger.info(f"Not found on VGSI: {not_found}")
    logger.info(f"Errors: {errors}")


def main():
    parser = argparse.ArgumentParser(description='Scrape missing parcels from Worcester MA GIS')
    parser.add_argument('--limit', type=int, help='Limit number of parcels to scrape')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be scraped without scraping')

    args = parser.parse_args()

    asyncio.run(scrape_missing_parcels(limit=args.limit, dry_run=args.dry_run))


if __name__ == '__main__':
    main()
