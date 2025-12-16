#!/usr/bin/env python3
"""
Test script to scrape a single street: Wachusett St
"""
import asyncio
import json
from datetime import datetime
from playwright.async_api import async_playwright

BASE_URL = "https://gis.vgsi.com/worcesterma"
STREET_NAME = "WACHUSETT ST"

async def scrape_wachusett_street():
    """Scrape all properties on Wachusett St."""

    print(f"Starting scrape for: {STREET_NAME}")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()
        page.set_default_timeout(30000)

        # Step 1: Go to Streets page
        print("\n[1] Navigating to Streets.aspx...")
        await page.goto(f"{BASE_URL}/Streets.aspx", wait_until="networkidle")
        await asyncio.sleep(2)

        # Take screenshot for debugging
        await page.screenshot(path="/home/user/datacollection/debug_streets_page.png")
        print("    Screenshot saved: debug_streets_page.png")

        # Step 2: Find and click on Wachusett St (or letter W first)
        print("\n[2] Looking for Wachusett St...")

        # First try clicking on letter 'W' if alphabetical navigation exists
        try:
            w_link = await page.query_selector("a:text('W')")
            if w_link:
                await w_link.click()
                await page.wait_for_load_state('networkidle')
                await asyncio.sleep(1)
                print("    Clicked 'W' for alphabetical filter")
        except Exception as e:
            print(f"    No alphabetical navigation found: {e}")

        # Find the street link
        street_link = None
        possible_selectors = [
            f"a:text-is('{STREET_NAME}')",
            f"a:text('{STREET_NAME}')",
            "a:text('WACHUSETT')",
            "a:text('Wachusett')",
        ]

        for selector in possible_selectors:
            try:
                street_link = await page.query_selector(selector)
                if street_link:
                    text = await street_link.text_content()
                    print(f"    Found street link: {text}")
                    break
            except:
                continue

        if not street_link:
            # List all visible links to debug
            print("\n    Available links on page:")
            all_links = await page.query_selector_all("a")
            for link in all_links[:30]:
                text = await link.text_content()
                if text and len(text.strip()) > 0:
                    print(f"      - {text.strip()}")

            await browser.close()
            return None

        # Click on the street
        await street_link.click()
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(2)

        await page.screenshot(path="/home/user/datacollection/debug_street_properties.png")
        print("    Screenshot saved: debug_street_properties.png")

        # Step 3: Extract all properties on this street
        print("\n[3] Extracting property listings...")

        properties = []

        # Look for property links (Parcel links)
        parcel_links = await page.query_selector_all("a[href*='Parcel']")

        if not parcel_links:
            # Try other patterns
            parcel_links = await page.query_selector_all("table tr td a")

        print(f"    Found {len(parcel_links)} potential property links")

        # Extract basic info from each link
        property_urls = []
        for link in parcel_links:
            href = await link.get_attribute('href')
            text = await link.text_content()
            if href and 'Parcel' in href:
                full_url = f"{BASE_URL}/{href}" if not href.startswith('http') else href
                property_urls.append({
                    'address': text.strip() if text else '',
                    'url': full_url
                })

        print(f"    Found {len(property_urls)} properties to scrape")

        # Step 4: Scrape details for each property (limit to first 5 for demo)
        print("\n[4] Scraping property details...")

        for idx, prop_info in enumerate(property_urls[:5], 1):  # Limit to 5 for demo
            print(f"\n    [{idx}/{min(5, len(property_urls))}] {prop_info['address']}")

            try:
                await page.goto(prop_info['url'], wait_until='networkidle')
                await asyncio.sleep(1)

                property_data = {
                    'address': prop_info['address'],
                    'url': prop_info['url'],
                    'scraped_at': datetime.now().isoformat(),
                }

                # Extract all visible data from the page
                # Owner info
                owner_selectors = [
                    "#MainContent_lblOwner",
                    "#ctl00_MainContent_lblOwner",
                    "span[id*='Owner']",
                    "td:has-text('Owner') + td",
                ]
                for sel in owner_selectors:
                    try:
                        el = await page.query_selector(sel)
                        if el:
                            text = await el.text_content()
                            if text and text.strip():
                                property_data['owner'] = text.strip()
                                break
                    except:
                        continue

                # Location
                for sel in ["#MainContent_lblLocation", "#ctl00_MainContent_lblLocation", "span[id*='Location']"]:
                    try:
                        el = await page.query_selector(sel)
                        if el:
                            text = await el.text_content()
                            if text:
                                property_data['location'] = text.strip()
                                break
                    except:
                        continue

                # Extract all label-value pairs from tables
                tables = await page.query_selector_all("table")
                details = {}

                for table in tables:
                    rows = await table.query_selector_all("tr")
                    for row in rows:
                        cells = await row.query_selector_all("td")
                        if len(cells) >= 2:
                            label = await cells[0].text_content()
                            value = await cells[1].text_content()
                            if label and value:
                                label = label.strip().rstrip(':')
                                value = value.strip()
                                if label and value and len(label) < 50:
                                    details[label] = value

                property_data['details'] = details

                # Look for photo
                photo_selectors = [
                    "img[id*='Photo']",
                    "img[id*='Image']",
                    "img[src*='Photo']",
                    "img[src*='GetImage']",
                ]
                photos = []
                for sel in photo_selectors:
                    imgs = await page.query_selector_all(sel)
                    for img in imgs:
                        src = await img.get_attribute('src')
                        if src and 'placeholder' not in src.lower():
                            full_src = f"{BASE_URL}/{src}" if not src.startswith('http') else src
                            photos.append(full_src)

                property_data['photos'] = list(set(photos))

                # Look for sketch/layout
                sketch_selectors = [
                    "img[id*='Sketch']",
                    "img[src*='Sketch']",
                    "img[src*='sketch']",
                ]
                sketches = []
                for sel in sketch_selectors:
                    imgs = await page.query_selector_all(sel)
                    for img in imgs:
                        src = await img.get_attribute('src')
                        if src:
                            full_src = f"{BASE_URL}/{src}" if not src.startswith('http') else src
                            sketches.append(full_src)

                property_data['layouts'] = list(set(sketches))

                properties.append(property_data)
                print(f"        Owner: {property_data.get('owner', 'N/A')}")
                print(f"        Details found: {len(details)} fields")

            except Exception as e:
                print(f"        Error: {e}")
                continue

        await browser.close()

        # Create output
        output = {
            'street': STREET_NAME,
            'scraped_at': datetime.now().isoformat(),
            'total_properties_found': len(property_urls),
            'properties_scraped': len(properties),
            'properties': properties
        }

        return output


async def main():
    result = await scrape_wachusett_street()

    if result:
        # Save to JSON
        output_file = "/home/user/datacollection/wachusett_st.json"
        with open(output_file, 'w', indent=2) as f:
            json.dump(result, f, indent=2)

        print("\n" + "=" * 60)
        print(f"SUCCESS! Data saved to: {output_file}")
        print("=" * 60)

        # Print summary
        print(f"\nStreet: {result['street']}")
        print(f"Total properties found: {result['total_properties_found']}")
        print(f"Properties scraped: {result['properties_scraped']}")

        return output_file
    else:
        print("\nFailed to scrape data")
        return None


if __name__ == "__main__":
    asyncio.run(main())
