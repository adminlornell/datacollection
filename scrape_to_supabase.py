#!/usr/bin/env python3
"""
Worcester MA Property Scraper - Supabase Only

Scrapes all property data from Worcester MA GIS website and stores
directly to Supabase. No local SQLite database required.

Usage:
    python scrape_to_supabase.py                     # Run full scrape (resumes automatically)
    python scrape_to_supabase.py --street "Main St"  # Scrape specific street
    python scrape_to_supabase.py --status            # Check progress
    python scrape_to_supabase.py --reset             # Reset progress and start fresh
    python scrape_to_supabase.py --streets-only      # Only fetch and save street list

Environment Variables:
    SUPABASE_URL - Your Supabase project URL
    SUPABASE_KEY - Your Supabase service role key

Features:
    - Street-by-street processing
    - Automatic resume capability
    - Real-time progress tracking in Supabase
    - All data stored directly to Supabase
"""
import asyncio
import argparse
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.scrapers.supabase_scraper import SupabaseScraper
from src.config import SUPABASE_URL, SUPABASE_KEY

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('supabase_scraper.log')
    ]
)
logger = logging.getLogger(__name__)


def check_supabase_config():
    """Check that Supabase is configured properly."""
    if not SUPABASE_URL:
        print("ERROR: SUPABASE_URL not configured.")
        print("Set it via environment variable or in src/config.py")
        sys.exit(1)
    
    if not SUPABASE_KEY:
        print("ERROR: SUPABASE_KEY not configured.")
        print("Set it via environment variable: export SUPABASE_KEY='your-service-role-key'")
        print("\nYou can find your service role key in:")
        print("  Supabase Dashboard → Settings → API → service_role key")
        sys.exit(1)


def print_status(scraper: SupabaseScraper):
    """Print current scraping status from Supabase."""
    print("\n" + "=" * 60)
    print("WORCESTER PROPERTY SCRAPING STATUS")
    print("=" * 60)
    
    stats = scraper.get_stats()
    progress = scraper.get_progress()
    
    print(f"\nStreets:")
    print(f"  Total: {stats.get('total_streets', 0)}")
    print(f"  Scraped: {stats.get('scraped_streets', 0)}")
    remaining_streets = stats.get('total_streets', 0) - stats.get('scraped_streets', 0)
    print(f"  Remaining: {remaining_streets}")
    
    print(f"\nProperties:")
    print(f"  Total scraped: {stats.get('total_properties', 0)}")
    
    if progress:
        print(f"\nCurrent Progress:")
        print(f"  Status: {progress.get('status', 'unknown')}")
        if progress.get('current_street'):
            print(f"  Current street: {progress.get('current_street')}")
        if progress.get('started_at'):
            print(f"  Started: {progress.get('started_at')}")
        if progress.get('updated_at'):
            print(f"  Last update: {progress.get('updated_at')}")
    
    print("\n" + "=" * 60)


async def run_full_scrape(scraper: SupabaseScraper, resume: bool = True):
    """Run the full scraping pipeline."""
    async with scraper:
        result = await scraper.run_full_scrape(resume=resume)
        return result


async def scrape_single_street(scraper: SupabaseScraper, street_name: str):
    """Scrape a single street by name."""
    # First, make sure we have streets in the database
    async with scraper:
        # Check if street exists
        result = scraper.supabase.table('worcester_streets').select('*').ilike('name', f'%{street_name}%').execute()
        
        if not result.data:
            logger.info(f"Street '{street_name}' not found in database. Fetching street list first...")
            streets = await scraper.scrape_all_streets()
            await scraper.save_streets_to_supabase(streets)
            
            # Try again
            result = scraper.supabase.table('worcester_streets').select('*').ilike('name', f'%{street_name}%').execute()
        
        if not result.data:
            print(f"ERROR: Street '{street_name}' not found.")
            print("\nAvailable streets matching your query: None")
            return
        
        if len(result.data) > 1:
            print(f"Multiple streets match '{street_name}':")
            for s in result.data[:10]:
                print(f"  - {s['name']}")
            print("\nPlease be more specific.")
            return
        
        street = result.data[0]
        logger.info(f"Scraping street: {street['name']}")
        
        prop_count = await scraper.scrape_street(street['name'], street['url'])
        print(f"\nScraped {prop_count} properties from {street['name']}")


async def fetch_streets_only(scraper: SupabaseScraper):
    """Only fetch and save the street list."""
    async with scraper:
        streets = await scraper.scrape_all_streets()
        saved = await scraper.save_streets_to_supabase(streets)
        print(f"\nSaved {saved} streets to Supabase")


def reset_progress(scraper: SupabaseScraper):
    """Reset all scraping progress."""
    print("Resetting scraping progress...")
    
    # Reset progress table
    scraper.supabase.table('worcester_scraping_progress').upsert({
        'task_name': 'worcester_full_scrape',
        'current_street': None,
        'total_streets': 0,
        'completed_streets': 0,
        'total_properties': 0,
        'completed_properties': 0,
        'status': 'pending',
        'started_at': None,
        'completed_at': None
    }, on_conflict='task_name').execute()
    
    # Reset all streets to unscraped
    scraper.supabase.table('worcester_streets').update({
        'scraped': False,
        'scraped_at': None,
        'property_count': 0
    }).neq('name', '').execute()
    
    print("Progress reset. All streets marked as unscraped.")
    print("Note: Property data in worcester_data_collection is preserved.")
    print("To clear property data, run: DELETE FROM worcester_data_collection;")


def main():
    parser = argparse.ArgumentParser(
        description='Worcester MA Property Scraper - Supabase Only',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scrape_to_supabase.py                     # Full scrape (resumes)
  python scrape_to_supabase.py --street "Main"     # Scrape Main Street
  python scrape_to_supabase.py --status            # Check progress
  python scrape_to_supabase.py --streets-only      # Just fetch street list
  python scrape_to_supabase.py --reset             # Reset and start over

Environment:
  SUPABASE_URL   Your Supabase project URL
  SUPABASE_KEY   Your Supabase service role key (not anon key)
        """
    )
    
    parser.add_argument('--street', type=str,
                        help='Scrape a specific street by name')
    parser.add_argument('--status', action='store_true',
                        help='Show current scraping progress')
    parser.add_argument('--reset', action='store_true',
                        help='Reset progress and start fresh')
    parser.add_argument('--streets-only', action='store_true',
                        help='Only fetch and save the street list')
    parser.add_argument('--no-resume', action='store_true',
                        help='Start fresh (scrape all streets, even if already done)')
    
    args = parser.parse_args()
    
    # Check configuration
    check_supabase_config()
    
    # Initialize scraper
    scraper = SupabaseScraper()
    
    try:
        if args.status:
            print_status(scraper)
            return
        
        if args.reset:
            reset_progress(scraper)
            return
        
        if args.streets_only:
            asyncio.run(fetch_streets_only(scraper))
            return
        
        if args.street:
            asyncio.run(scrape_single_street(scraper, args.street))
            return
        
        # Default: run full scrape
        resume = not args.no_resume
        result = asyncio.run(run_full_scrape(scraper, resume=resume))
        
        print("\n" + "=" * 60)
        print("SCRAPING COMPLETE")
        print("=" * 60)
        print(f"Time elapsed: {result.get('elapsed', 'N/A')}")
        print(f"Streets scraped: {result.get('streets_scraped', 0)}")
        print(f"Properties scraped: {result.get('properties_scraped', 0)}")
        print("=" * 60)
        
    except KeyboardInterrupt:
        logger.info("\nScraping interrupted by user. Progress saved to Supabase.")
        logger.info("Run again to resume from where you left off.")
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        raise


if __name__ == '__main__':
    main()

