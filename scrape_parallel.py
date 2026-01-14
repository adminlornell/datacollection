#!/usr/bin/env python3
"""
Parallel Worcester Property Scraper

Runs multiple browser instances in parallel to speed up scraping.
Each worker processes different streets independently.
"""

import asyncio
import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict
from dotenv import load_dotenv
from supabase import create_client

# Load environment variables from .env file in the same directory as this script
SCRIPT_DIR = Path(__file__).parent.resolve()
load_dotenv(SCRIPT_DIR / '.env')

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    print(f"ERROR: Missing Supabase credentials!")
    print(f"  Looking for .env at: {SCRIPT_DIR / '.env'}")
    print(f"  SUPABASE_URL: {'set' if SUPABASE_URL else 'MISSING'}")
    print(f"  SUPABASE_KEY: {'set' if SUPABASE_KEY else 'MISSING'}")
    sys.exit(1)

from src.scrapers.supabase_scraper import SupabaseScraper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('ParallelScraper')


class ParallelScraper:
    """Manages multiple scraper workers for parallel execution."""
    
    def __init__(self, num_workers: int = 3):
        self.num_workers = num_workers
        self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        self.streets_queue: asyncio.Queue = asyncio.Queue()
        self.stats = {
            'total_properties': 0,
            'total_streets': 0,
            'errors': 0,
            'start_time': None
        }
        self.stats_lock = asyncio.Lock()
        
    def get_unscraped_streets(self) -> List[Dict]:
        """Get list of streets that haven't been scraped yet."""
        result = self.supabase.table('worcester_streets').select('name, url').eq('scraped', False).execute()
        return result.data
    
    async def worker(self, worker_id: int):
        """
        Worker coroutine that processes streets from the queue.
        Each worker has its own browser instance.
        """
        logger.info(f"[Worker {worker_id}] Starting...")
        
        scraper = SupabaseScraper()
        
        try:
            await scraper.start_browser()
            logger.info(f"[Worker {worker_id}] Browser ready")
            
            while True:
                try:
                    # Get next street from queue (with timeout)
                    try:
                        street = await asyncio.wait_for(
                            self.streets_queue.get(),
                            timeout=5.0
                        )
                    except asyncio.TimeoutError:
                        # Check if queue is empty and no more work
                        if self.streets_queue.empty():
                            logger.info(f"[Worker {worker_id}] Queue empty, finishing")
                            break
                        continue
                    
                    street_name = street['name']
                    street_url = street['url']
                    
                    logger.info(f"[Worker {worker_id}] Processing: {street_name}")
                    
                    try:
                        # Scrape the street
                        prop_count = await scraper.scrape_street(street_name, street_url)
                        
                        async with self.stats_lock:
                            self.stats['total_properties'] += prop_count
                            self.stats['total_streets'] += 1
                        
                        logger.info(f"[Worker {worker_id}] Completed {street_name}: {prop_count} properties")
                        
                    except Exception as e:
                        logger.error(f"[Worker {worker_id}] Error on {street_name}: {e}")
                        async with self.stats_lock:
                            self.stats['errors'] += 1
                    
                    self.streets_queue.task_done()
                    
                    # Small delay between streets to be nice to the server
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"[Worker {worker_id}] Worker error: {e}")
                    continue
                    
        finally:
            await scraper.close_browser()
            logger.info(f"[Worker {worker_id}] Shut down")
    
    async def run(self, max_streets: int = None):
        """
        Run the parallel scraper.
        
        Args:
            max_streets: Maximum number of streets to process (None = all)
        """
        self.stats['start_time'] = datetime.utcnow()
        
        # Get unscraped streets
        logger.info("Fetching unscraped streets...")
        streets = self.get_unscraped_streets()
        
        if max_streets:
            streets = streets[:max_streets]
        
        logger.info(f"Found {len(streets)} streets to scrape")
        logger.info(f"Starting {self.num_workers} parallel workers")
        
        if not streets:
            logger.info("No streets to process!")
            return self.stats
        
        # Add streets to queue
        for street in streets:
            await self.streets_queue.put(street)
        
        # Create and start workers
        workers = [
            asyncio.create_task(self.worker(i + 1))
            for i in range(self.num_workers)
        ]
        
        # Wait for all streets to be processed
        await self.streets_queue.join()
        
        # Cancel workers (they should exit on their own, but just in case)
        for worker in workers:
            worker.cancel()
        
        # Wait for workers to finish
        await asyncio.gather(*workers, return_exceptions=True)
        
        # Print final stats
        elapsed = datetime.utcnow() - self.stats['start_time']
        
        logger.info("\n" + "=" * 60)
        logger.info("PARALLEL SCRAPING COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Time elapsed: {elapsed}")
        logger.info(f"Workers used: {self.num_workers}")
        logger.info(f"Streets processed: {self.stats['total_streets']}")
        logger.info(f"Properties scraped: {self.stats['total_properties']}")
        logger.info(f"Errors: {self.stats['errors']}")
        if self.stats['total_streets'] > 0:
            logger.info(f"Avg properties/street: {self.stats['total_properties']/self.stats['total_streets']:.1f}")
            logger.info(f"Avg time/street: {elapsed.total_seconds()/self.stats['total_streets']:.1f}s")
        logger.info("=" * 60)
        
        return self.stats


async def ensure_streets_exist():
    """Make sure streets have been scraped and saved to Supabase."""
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    result = supabase.table('worcester_streets').select('*', count='exact').execute()
    
    if result.count == 0:
        logger.info("No streets in database. Running initial street scrape...")
        scraper = SupabaseScraper()
        await scraper.start_browser()
        try:
            streets = await scraper.scrape_all_streets()
            await scraper.save_streets_to_supabase(streets)
        finally:
            await scraper.close_browser()
    else:
        logger.info(f"Found {result.count} streets in database")


async def main():
    parser = argparse.ArgumentParser(description='Parallel Worcester Property Scraper')
    parser.add_argument('--workers', '-w', type=int, default=3,
                        help='Number of parallel workers (default: 3)')
    parser.add_argument('--max-streets', '-m', type=int, default=None,
                        help='Maximum streets to process (default: all)')
    parser.add_argument('--status', '-s', action='store_true',
                        help='Show current status and exit')
    
    args = parser.parse_args()
    
    if args.status:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        streets = supabase.table('worcester_streets').select('*', count='exact').execute()
        scraped = supabase.table('worcester_streets').select('*', count='exact').eq('scraped', True).execute()
        props = supabase.table('worcester_data_collection').select('*', count='exact').execute()
        
        print(f"\nCurrent Status:")
        print(f"  Streets: {scraped.count}/{streets.count} scraped ({scraped.count/streets.count*100:.1f}%)")
        print(f"  Properties: {props.count}")
        print(f"  Remaining streets: {streets.count - scraped.count}")
        return
    
    # Ensure streets exist
    await ensure_streets_exist()
    
    # Run parallel scraper
    scraper = ParallelScraper(num_workers=args.workers)
    await scraper.run(max_streets=args.max_streets)


if __name__ == '__main__':
    asyncio.run(main())

