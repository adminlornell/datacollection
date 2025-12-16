#!/usr/bin/env python3
"""
Scraper for a single street from Worcester MA VGSI GIS.
Based on actual HTML structure from gis.vgsi.com/worcesterma

Usage:
    python scrape_single_street.py "WACHUSETT ST"
    python scrape_single_street.py "MAIN ST" --limit 10
"""
import asyncio
import json
import re
import sys
from datetime import datetime
from urllib.parse import urljoin
from playwright.async_api import async_playwright

BASE_URL = "https://gis.vgsi.com/worcesterma"


class WorcesterStreetScraper:
    def __init__(self, street_name: str, limit: int = None):
        self.street_name = street_name.upper()
        self.limit = limit
        self.browser = None
        self.page = None

    async def start(self):
        """Initialize browser."""
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=True)
        context = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        self.page = await context.new_page()
        self.page.set_default_timeout(30000)

    async def close(self):
        """Close browser."""
        if self.browser:
            await self.browser.close()

    async def get_text(self, selector: str, default: str = None) -> str:
        """Safely extract text from selector."""
        try:
            el = await self.page.query_selector(selector)
            if el:
                text = await el.text_content()
                return text.strip() if text else default
        except:
            pass
        return default

    async def get_table_rows(self, table_selector: str) -> list:
        """Extract rows from a table as list of dicts."""
        rows = []
        try:
            table = await self.page.query_selector(table_selector)
            if not table:
                return rows

            # Get headers
            header_els = await table.query_selector_all("tr.HeaderStyle th")
            headers = []
            for h in header_els:
                text = await h.text_content()
                headers.append(text.strip() if text else "")

            # Get data rows
            row_els = await table.query_selector_all("tr.RowStyle, tr.AltRowStyle")
            for row_el in row_els:
                cells = await row_el.query_selector_all("td")
                cell_texts = []
                for cell in cells:
                    text = await cell.text_content()
                    cell_texts.append(text.strip() if text else "")

                if headers and len(cell_texts) == len(headers):
                    rows.append(dict(zip(headers, cell_texts)))
                else:
                    rows.append(cell_texts)
        except Exception as e:
            print(f"    Error extracting table: {e}")
        return rows

    async def scrape_street(self) -> dict:
        """Scrape all properties on the street."""
        print(f"\n{'='*60}")
        print(f"Scraping: {self.street_name}")
        print(f"{'='*60}")

        await self.start()

        try:
            # Step 1: Navigate to street listing
            street_url = f"{BASE_URL}/Streets.aspx?Name={self.street_name.replace(' ', '%20')}"
            print(f"\n[1] Navigating to street listing...")
            print(f"    URL: {street_url}")

            await self.page.goto(street_url, wait_until='networkidle')
            await asyncio.sleep(2)

            # Step 2: Extract property links
            print(f"\n[2] Extracting property links...")
            property_links = await self.page.query_selector_all("a[href*='Parcel.aspx']")

            properties_to_scrape = []
            for link in property_links:
                href = await link.get_attribute('href')
                text = await link.text_content()
                if href and 'pid=' in href.lower():
                    # Extract PID
                    pid_match = re.search(r'pid=(\d+)', href, re.I)
                    if pid_match:
                        properties_to_scrape.append({
                            'pid': pid_match.group(1),
                            'address': text.strip() if text else '',
                            'url': urljoin(BASE_URL + '/', href)
                        })

            print(f"    Found {len(properties_to_scrape)} properties")

            if self.limit:
                properties_to_scrape = properties_to_scrape[:self.limit]
                print(f"    Limited to {self.limit} properties")

            # Step 3: Scrape each property
            print(f"\n[3] Scraping property details...")
            properties = []

            for idx, prop_info in enumerate(properties_to_scrape, 1):
                print(f"\n    [{idx}/{len(properties_to_scrape)}] {prop_info['address']} (PID: {prop_info['pid']})")

                try:
                    property_data = await self.scrape_property(prop_info)
                    properties.append(property_data)
                    await asyncio.sleep(1)  # Rate limiting
                except Exception as e:
                    print(f"        Error: {e}")
                    continue

            return {
                'street': self.street_name,
                'scraped_at': datetime.now().isoformat(),
                'total_properties_found': len(property_links),
                'properties_scraped': len(properties),
                'properties': properties
            }

        finally:
            await self.close()

    async def scrape_property(self, prop_info: dict) -> dict:
        """Scrape detailed property information."""
        await self.page.goto(prop_info['url'], wait_until='networkidle')
        await asyncio.sleep(1)

        data = {
            'pid': prop_info['pid'],
            'url': prop_info['url'],
            'scraped_at': datetime.now().isoformat()
        }

        # === BASIC INFO ===
        data['location'] = await self.get_text("#MainContent_lblLocation")
        data['mblu'] = await self.get_text("#MainContent_lblMblu")
        data['acct_number'] = await self.get_text("#MainContent_lblAcctNum")
        data['building_count'] = await self.get_text("#MainContent_lblBldCount")

        # === OWNER INFO ===
        data['owner'] = {
            'name': await self.get_text("#MainContent_lblOwner") or await self.get_text("#MainContent_lblGenOwner"),
            'co_owner': await self.get_text("#MainContent_lblCoOwner"),
            'mailing_address': await self.get_text("#MainContent_lblAddr1")
        }

        # === CURRENT SALE ===
        data['current_sale'] = {
            'price': await self.get_text("#MainContent_lblPrice"),
            'date': await self.get_text("#MainContent_lblSaleDate"),
            'book_page': await self.get_text("#MainContent_lblBp"),
            'certificate': await self.get_text("#MainContent_lblCertificate"),
            'instrument': await self.get_text("#MainContent_lblInstrument")
        }

        # === CURRENT ASSESSMENT ===
        data['assessment'] = {
            'total': await self.get_text("#MainContent_lblGenAssessment")
        }

        # Try to get detailed assessment from table
        assessment_rows = await self.get_table_rows("#MainContent_grdCurrentValueAsmt")
        if assessment_rows:
            row = assessment_rows[0]
            if isinstance(row, dict):
                data['assessment']['valuation_year'] = row.get('Valuation Year')
                data['assessment']['improvements'] = row.get('Improvements')
                data['assessment']['land'] = row.get('Land')
                data['assessment']['total'] = row.get('Total')

        # === BUILDING INFO ===
        data['building'] = {
            'year_built': await self.get_text("#MainContent_ctl01_lblYearBuilt"),
            'living_area_sqft': await self.get_text("#MainContent_ctl01_lblBldArea"),
            'replacement_cost': await self.get_text("#MainContent_ctl01_lblRcn"),
            'percent_good': await self.get_text("#MainContent_ctl01_lblPctGood"),
            'rcnld': await self.get_text("#MainContent_ctl01_lblRcnld"),
            'attributes': {},
            'sub_areas': []
        }

        # Building attributes from table
        attr_rows = await self.get_table_rows("#MainContent_ctl01_grdCns")
        for row in attr_rows:
            if isinstance(row, dict):
                field = row.get('Field', '').rstrip(':')
                desc = row.get('Description', '')
                if field:
                    # Convert to snake_case key
                    key = field.lower().replace(' ', '_').replace('/', '_')
                    data['building']['attributes'][key] = desc

        # Building sub-areas
        subarea_rows = await self.get_table_rows("#MainContent_ctl01_grdSub")
        for row in subarea_rows:
            if isinstance(row, dict):
                data['building']['sub_areas'].append({
                    'code': row.get('Code'),
                    'description': row.get('Description'),
                    'gross_area': row.get('Gross\nArea', row.get('Gross Area')),
                    'living_area': row.get('Living\nArea', row.get('Living Area'))
                })

        # === LAND INFO ===
        data['land'] = {
            'use_code': await self.get_text("#MainContent_lblUseCode"),
            'description': await self.get_text("#MainContent_lblUseCodeDescription"),
            'zone': await self.get_text("#MainContent_lblZone"),
            'neighborhood': await self.get_text("#MainContent_lblNbhd"),
            'size_sqft': await self.get_text("#MainContent_lblLndSf"),
            'depth': await self.get_text("#MainContent_lblDepth"),
            'assessed_value': await self.get_text("#MainContent_lblLndAsmt")
        }

        # === SALES HISTORY ===
        data['sales_history'] = await self.get_table_rows("#MainContent_grdSales")

        # === VALUATION HISTORY ===
        data['valuation_history'] = await self.get_table_rows("#MainContent_grdHistoryValuesAsmt")

        # === PHOTOS ===
        data['photos'] = []
        photo_img = await self.page.query_selector("#MainContent_ctl01_imgPhoto")
        if photo_img:
            src = await photo_img.get_attribute('src')
            if src:
                data['photos'].append({
                    'type': 'building',
                    'url': src,
                    'description': 'Building Photo'
                })

        # === LAYOUTS/SKETCHES ===
        data['layouts'] = []
        sketch_img = await self.page.query_selector("#MainContent_ctl01_imgSketch")
        if sketch_img:
            src = await sketch_img.get_attribute('src')
            if src:
                data['layouts'].append({
                    'type': 'sketch',
                    'url': src,
                    'description': 'Building Layout'
                })

        # === EXTRA FEATURES ===
        data['extra_features'] = await self.get_table_rows("#MainContent_grdXf")

        # === OUTBUILDINGS ===
        data['outbuildings'] = await self.get_table_rows("#MainContent_grdOb")

        print(f"        Owner: {data['owner']['name']}")
        print(f"        Assessment: {data['assessment'].get('total', 'N/A')}")
        print(f"        Year Built: {data['building']['year_built']}")
        print(f"        Living Area: {data['building']['living_area_sqft']} sqft")

        return data


async def main():
    import argparse
    parser = argparse.ArgumentParser(description='Scrape properties from a Worcester MA street')
    parser.add_argument('street', help='Street name (e.g., "WACHUSETT ST")')
    parser.add_argument('--limit', type=int, help='Limit number of properties to scrape')
    parser.add_argument('--output', '-o', help='Output JSON file path')

    args = parser.parse_args()

    scraper = WorcesterStreetScraper(args.street, limit=args.limit)
    result = await scraper.scrape_street()

    # Determine output filename
    output_file = args.output or f"{args.street.lower().replace(' ', '_')}.json"

    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"\n{'='*60}")
    print(f"SUCCESS!")
    print(f"{'='*60}")
    print(f"Street: {result['street']}")
    print(f"Properties found: {result['total_properties_found']}")
    print(f"Properties scraped: {result['properties_scraped']}")
    print(f"Output saved to: {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
