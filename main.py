#!/usr/bin/env python3
"""
Worcester MA Property Records Scraper

Main orchestrator script that coordinates the scraping of all property
records from the Worcester MA GIS website (gis.vgsi.com/worcesterma).

Usage:
    python main.py                    # Run full scraping pipeline
    python main.py --streets-only     # Only scrape street list
    python main.py --properties-only  # Only scrape property listings
    python main.py --details-only     # Only scrape property details
    python main.py --download-only    # Only download photos/layouts
    python main.py --export           # Export data to CSV/JSON
    python main.py --status           # Show scraping progress
    python main.py --enrich           # Enrich owner info with AI agents
    python main.py --enrich-parcel X  # Enrich specific parcel

Features:
    - Automatic resume capability
    - Progress tracking
    - Rate limiting to be respectful to the server
    - Concurrent media downloads
    - Data export to CSV/JSON
    - AI-powered owner research (MA SOS, OpenCorporates, SEC EDGAR)
"""
import asyncio
import argparse
import sys
import json
from datetime import datetime
from pathlib import Path

from src.models import init_database, Street, Property, PropertyPhoto, PropertyLayout, ScrapingProgress
from src.scrapers.street_scraper import StreetScraper
from src.scrapers.property_scraper import PropertyScraper
from src.scrapers.detail_scraper import PropertyDetailScraper
from src.scrapers.media_downloader import MediaDownloader
from src.config import DATABASE_PATH, EXPORTS_DIR

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('scraper.log')
    ]
)
logger = logging.getLogger(__name__)


class WorcesterPropertyScraper:
    """
    Main orchestrator for the Worcester property scraping pipeline.

    Pipeline stages:
    1. Scrape all streets from Streets.aspx
    2. For each street, scrape all property listings
    3. For each property, scrape detailed information
    4. Download all photos and layouts
    """

    def __init__(self):
        self.engine, self.Session = init_database(DATABASE_PATH)
        self.session = self.Session()

    def close(self):
        """Close database session."""
        self.session.close()

    async def run_full_pipeline(self, resume: bool = True):
        """Run the complete scraping pipeline."""
        logger.info("=" * 60)
        logger.info("Starting Worcester MA Property Scraping Pipeline")
        logger.info("=" * 60)

        start_time = datetime.now()

        try:
            # Stage 1: Scrape streets
            logger.info("\n[Stage 1/4] Scraping street list...")
            await self.scrape_streets()

            # Stage 2: Scrape property listings per street
            logger.info("\n[Stage 2/4] Scraping property listings...")
            await self.scrape_properties(resume=resume)

            # Stage 3: Scrape property details
            logger.info("\n[Stage 3/4] Scraping property details...")
            await self.scrape_property_details(resume=resume)

            # Stage 4: Download media
            logger.info("\n[Stage 4/4] Downloading photos and layouts...")
            await self.download_media(resume=resume)

            elapsed = datetime.now() - start_time
            logger.info("=" * 60)
            logger.info(f"Pipeline completed in {elapsed}")
            logger.info("=" * 60)

            self.print_status()

        except KeyboardInterrupt:
            logger.info("\nScraping interrupted by user. Progress has been saved.")
            logger.info("Run again to resume from where you left off.")
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            raise

    async def scrape_streets(self):
        """Scrape all streets from the website."""
        # Check if already done
        progress = self.session.query(ScrapingProgress).filter_by(task_name='streets').first()
        if progress and progress.status == 'completed':
            logger.info(f"Streets already scraped ({progress.total_items} streets). Skipping.")
            return

        async with StreetScraper(self.session) as scraper:
            count = await scraper.run()
            logger.info(f"Scraped {count} streets")

    async def scrape_properties(self, resume: bool = True):
        """Scrape property listings for all streets."""
        async with PropertyScraper(self.session) as scraper:
            count = await scraper.run(resume=resume)
            logger.info(f"Scraped {count} properties")

    async def scrape_property_details(self, resume: bool = True, limit: int = None):
        """Scrape detailed information for all properties."""
        async with PropertyDetailScraper(self.session) as scraper:
            count = await scraper.run(resume=resume, limit=limit)
            logger.info(f"Scraped details for {count} properties")

    async def download_media(self, resume: bool = True):
        """Download all photos and layouts."""
        downloader = MediaDownloader(self.session)
        stats = await downloader.run(resume=resume)
        logger.info(f"Downloaded {stats['photos_downloaded']} photos, {stats['layouts_downloaded']} layouts")

    def print_status(self):
        """Print current scraping progress."""
        print("\n" + "=" * 60)
        print("SCRAPING STATUS")
        print("=" * 60)

        # Streets
        total_streets = self.session.query(Street).count()
        scraped_streets = self.session.query(Street).filter_by(scraped=True).count()
        print(f"\nStreets: {scraped_streets}/{total_streets} scraped")

        # Properties
        total_properties = self.session.query(Property).count()
        scraped_properties = self.session.query(Property).filter_by(scraped=True).count()
        print(f"Properties: {scraped_properties}/{total_properties} details scraped")

        # Photos
        total_photos = self.session.query(PropertyPhoto).count()
        downloaded_photos = self.session.query(PropertyPhoto).filter_by(downloaded=True).count()
        print(f"Photos: {downloaded_photos}/{total_photos} downloaded")

        # Layouts
        total_layouts = self.session.query(PropertyLayout).count()
        downloaded_layouts = self.session.query(PropertyLayout).filter_by(downloaded=True).count()
        print(f"Layouts: {downloaded_layouts}/{total_layouts} downloaded")

        # Sample property data
        sample = self.session.query(Property).filter(Property.total_value != None).first()
        if sample:
            print(f"\nSample property:")
            print(f"  Address: {sample.address}")
            print(f"  Owner: {sample.owner_name}")
            print(f"  Year Built: {sample.year_built}")
            print(f"  Living Area: {sample.living_area} sq ft")
            print(f"  Bedrooms: {sample.bedrooms}")
            print(f"  Total Value: ${sample.total_value:,.2f}" if sample.total_value else "  Total Value: N/A")

        print("\n" + "=" * 60)

    def export_data(self, format: str = 'both'):
        """
        Export scraped data to files.

        Args:
            format: 'csv', 'json', or 'both'
        """
        import pandas as pd

        logger.info(f"Exporting data to {format} format...")

        # Get all properties with their details
        properties = self.session.query(Property).all()

        # Convert to list of dicts
        data = []
        for prop in properties:
            record = {
                'parcel_id': prop.parcel_id,
                'address': prop.address,
                'location': prop.location,
                'owner_name': prop.owner_name,
                'owner_address': prop.owner_address,
                'property_type': prop.property_type,
                'land_use': prop.land_use,
                'zoning': prop.zoning,
                'neighborhood': prop.neighborhood,
                'year_built': prop.year_built,
                'living_area': prop.living_area,
                'total_rooms': prop.total_rooms,
                'bedrooms': prop.bedrooms,
                'bathrooms': prop.bathrooms,
                'stories': prop.stories,
                'building_style': prop.building_style,
                'exterior_wall': prop.exterior_wall,
                'roof_type': prop.roof_type,
                'heating': prop.heating,
                'cooling': prop.cooling,
                'lot_size': prop.lot_size,
                'frontage': prop.frontage,
                'depth': prop.depth,
                'land_value': prop.land_value,
                'building_value': prop.building_value,
                'total_value': prop.total_value,
                'detail_url': prop.detail_url,
            }

            # Get street name
            if prop.street:
                record['street_name'] = prop.street.name

            # Get photo count
            record['photo_count'] = len(prop.photos)
            record['layout_count'] = len(prop.layouts)

            data.append(record)

        if not data:
            logger.warning("No data to export")
            return

        df = pd.DataFrame(data)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if format in ['csv', 'both']:
            csv_path = EXPORTS_DIR / f'worcester_properties_{timestamp}.csv'
            df.to_csv(csv_path, index=False)
            logger.info(f"Exported {len(data)} properties to {csv_path}")

        if format in ['json', 'both']:
            json_path = EXPORTS_DIR / f'worcester_properties_{timestamp}.json'
            df.to_json(json_path, orient='records', indent=2)
            logger.info(f"Exported {len(data)} properties to {json_path}")

        # Also export sales history separately
        sales_data = []
        for prop in properties:
            if prop.sales_history:
                try:
                    sales = json.loads(prop.sales_history)
                    for sale in sales:
                        sale['parcel_id'] = prop.parcel_id
                        sale['address'] = prop.address
                        sales_data.append(sale)
                except json.JSONDecodeError:
                    pass

        if sales_data:
            sales_df = pd.DataFrame(sales_data)
            if format in ['csv', 'both']:
                sales_csv = EXPORTS_DIR / f'worcester_sales_history_{timestamp}.csv'
                sales_df.to_csv(sales_csv, index=False)
                logger.info(f"Exported {len(sales_data)} sales records to {sales_csv}")


def main():
    parser = argparse.ArgumentParser(
        description='Worcester MA Property Records Scraper',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                    # Run full pipeline
  python main.py --streets-only     # Just scrape streets
  python main.py --status           # Check progress
  python main.py --export           # Export to CSV/JSON
  python main.py --no-resume        # Start fresh (ignore previous progress)
  python main.py --enrich --limit 5 # Enrich 5 company owners
  python main.py --enrich-parcel 123 --enrich-deep  # Deep research specific parcel
        """
    )

    parser.add_argument('--streets-only', action='store_true',
                        help='Only scrape the street list')
    parser.add_argument('--properties-only', action='store_true',
                        help='Only scrape property listings (requires streets)')
    parser.add_argument('--details-only', action='store_true',
                        help='Only scrape property details (requires properties)')
    parser.add_argument('--download-only', action='store_true',
                        help='Only download photos and layouts')
    parser.add_argument('--export', action='store_true',
                        help='Export data to CSV and JSON')
    parser.add_argument('--status', action='store_true',
                        help='Show current scraping progress')
    parser.add_argument('--no-resume', action='store_true',
                        help='Start fresh, ignore previous progress')
    parser.add_argument('--limit', type=int, default=None,
                        help='Limit number of items to process (for testing)')
    parser.add_argument('--export-format', choices=['csv', 'json', 'both'],
                        default='both', help='Export format (default: both)')

    # Owner enrichment options
    parser.add_argument('--enrich', action='store_true',
                        help='Enrich owner information using AI agents')
    parser.add_argument('--enrich-parcel', type=str,
                        help='Enrich a specific parcel ID')
    parser.add_argument('--enrich-deep', action='store_true',
                        help='Perform deep ownership research (multiple iterations)')
    parser.add_argument('--llm', type=str, default='openrouter/meta-llama/llama-3.3-70b-instruct:free',
                        help='LLM model for enrichment (default: openrouter/meta-llama/llama-3.3-70b-instruct:free)')

    args = parser.parse_args()

    scraper = WorcesterPropertyScraper()

    try:
        if args.status:
            scraper.print_status()
            return

        if args.enrich or args.enrich_parcel:
            from src.enrichment import OwnerEnricher
            enricher = OwnerEnricher(
                db_path=DATABASE_PATH,
                llm=args.llm,
                verbose=True
            )
            if args.enrich_parcel:
                result = enricher.enrich_property(
                    parcel_id=args.enrich_parcel,
                    deep=args.enrich_deep
                )
                if result:
                    print("\n" + "="*60)
                    print("OWNERSHIP RESEARCH RESULT")
                    print("="*60)
                    print(result.model_dump_json(indent=2))
            else:
                limit = args.limit or 5
                results = enricher.enrich_batch(
                    limit=limit,
                    company_only=True,
                    deep=args.enrich_deep
                )
                report = enricher.generate_report(results)
                print(report)
            return

        if args.export:
            scraper.export_data(format=args.export_format)
            return

        resume = not args.no_resume

        if args.streets_only:
            asyncio.run(scraper.scrape_streets())
        elif args.properties_only:
            asyncio.run(scraper.scrape_properties(resume=resume))
        elif args.details_only:
            asyncio.run(scraper.scrape_property_details(resume=resume, limit=args.limit))
        elif args.download_only:
            asyncio.run(scraper.download_media(resume=resume))
        else:
            asyncio.run(scraper.run_full_pipeline(resume=resume))

    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
    finally:
        scraper.close()


if __name__ == '__main__':
    main()
