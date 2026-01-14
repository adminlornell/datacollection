#!/usr/bin/env python3
"""
Script to scrape a single parcel from the VGSI website and save to Supabase.
"""
import asyncio
import sys
import os
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from src.scrapers.supabase_scraper import SupabaseScraper
from src.config import SUPABASE_URL, SUPABASE_KEY


async def scrape_parcel(url: str):
    """
    Scrape a single parcel URL and save to Supabase.
    
    Args:
        url: Full parcel URL (e.g., https://gis.vgsi.com/worcesterma/Parcel.aspx?pid=1491)
    """
    # Extract parcel ID from URL
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    parcel_id = params.get('pid', [None])[0]
    
    if not parcel_id:
        print(f"Error: Could not extract parcel ID from URL: {url}")
        return
    
    print(f"Scraping parcel ID: {parcel_id}")
    print(f"URL: {url}")
    
    # Initialize scraper
    scraper = SupabaseScraper(SUPABASE_URL, SUPABASE_KEY)
    
    try:
        await scraper.start_browser()
        
        # Extract street name from URL or use a placeholder
        # For single parcel scraping, we'll try to extract it from the page
        street_name = "UNKNOWN"  # Will be updated if we can extract it
        
        # Scrape the property details
        print(f"\nNavigating to parcel page...")
        details = await scraper.scrape_property_details(
            parcel_id=parcel_id,
            detail_url=url,
            street_name=street_name
        )
        
        if details:
            # Try to extract street name from the scraped data
            location = details.get('basic_info', {}).get('location', '')
            if location:
                # Try to extract street name from location
                parts = location.split(',')
                if parts:
                    street_part = parts[0].strip()
                    # Extract street name (everything after the number)
                    import re
                    match = re.search(r'\d+\s+(.+?)(?:\s+(?:ST|AVE|RD|DR|LN|CT|PL|WAY|CIR|BLVD))', street_part.upper())
                    if match:
                        street_name = match.group(1).strip()
                    else:
                        # Fallback: try to get street from location
                        words = street_part.split()
                        if len(words) > 1:
                            # Assume street name is after the number
                            street_name = ' '.join(words[1:]).strip()
            
            # Update street_name in details
            details['street_name'] = street_name
            
            # Save to Supabase
            print(f"\nSaving to Supabase...")
            success = scraper._save_property_to_supabase(details)
            
            if success:
                print(f"\n✅ Successfully scraped and saved parcel {parcel_id}")
                print(f"   Street: {street_name}")
                print(f"   Location: {location}")
            else:
                print(f"\n❌ Failed to save parcel {parcel_id} to Supabase")
        else:
            print(f"\n❌ Failed to scrape parcel {parcel_id}")
            
    except Exception as e:
        print(f"\n❌ Error scraping parcel: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await scraper.close_browser()


async def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python scrape_single_parcel.py <parcel_url>")
        print("Example: python scrape_single_parcel.py 'https://gis.vgsi.com/worcesterma/Parcel.aspx?pid=1491'")
        sys.exit(1)
    
    url = sys.argv[1]
    await scrape_parcel(url)


if __name__ == "__main__":
    asyncio.run(main())

