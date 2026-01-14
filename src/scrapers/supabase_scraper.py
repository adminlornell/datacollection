"""
Unified Supabase-only scraper for Worcester MA property data.

This scraper handles the complete pipeline:
1. Scrape all streets from the VGSI website
2. For each street, scrape all property listings
3. For each property, scrape detailed information
4. Save everything directly to Supabase (no SQLite)

Features:
- Street-by-street processing with progress tracking
- Automatic resume capability via Supabase state
- Real-time progress updates
"""
import asyncio
import re
import json
import ssl
from datetime import datetime
from typing import Dict, Optional, List, Any
from urllib.parse import urljoin, parse_qs, urlparse

import aiohttp
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from supabase import create_client, Client

from ..config import (
    BASE_URL, STREETS_URL, SUPABASE_URL, SUPABASE_KEY,
    HEADLESS, SLOW_MO, TIMEOUT, USER_AGENT, REQUEST_DELAY, MAX_RETRIES
)

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


class SupabaseScraper:
    """
    Unified scraper that saves all data directly to Supabase.
    
    Handles:
    - Street discovery and tracking
    - Property listing extraction
    - Detailed property scraping
    - Progress tracking and resume capability
    """

    def __init__(self, supabase_url: str = None, supabase_key: str = None):
        """
        Initialize the Supabase scraper.
        
        Args:
            supabase_url: Supabase project URL (defaults to config)
            supabase_key: Supabase API key (defaults to config)
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Initialize Supabase client
        url = supabase_url or SUPABASE_URL
        key = supabase_key or SUPABASE_KEY
        
        if not url or not key:
            raise ValueError("Supabase URL and key are required. Set SUPABASE_URL and SUPABASE_KEY environment variables.")
        
        self.supabase: Client = create_client(url, key)
        self.logger.info("Supabase client initialized")
        
        # Browser components (initialized on start)
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._playwright = None

    async def __aenter__(self):
        await self.start_browser()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_browser()

    async def start_browser(self):
        """Initialize Playwright browser."""
        self.logger.info("Starting browser...")
        self._playwright = await async_playwright().start()
        
        self.browser = await self._playwright.chromium.launch(
            headless=HEADLESS,
            slow_mo=SLOW_MO
        )
        
        self.context = await self.browser.new_context(
            user_agent=USER_AGENT,
            viewport={'width': 1920, 'height': 1080}
        )
        
        self.page = await self.context.new_page()
        self.page.set_default_timeout(TIMEOUT)
        
        self.logger.info("Browser started successfully")

    async def close_browser(self):
        """Close browser and cleanup."""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()
        self.logger.info("Browser closed")

    # =========================================================================
    # NAVIGATION UTILITIES
    # =========================================================================

    async def navigate(self, url: str, wait_for: str = "networkidle"):
        """Navigate to a URL with retry logic."""
        for attempt in range(MAX_RETRIES):
            try:
                self.logger.debug(f"Navigating to: {url}")
                await self.page.goto(url, wait_until=wait_for)
                await self.delay()
                return True
            except Exception as e:
                self.logger.warning(f"Navigation attempt {attempt + 1} failed: {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    self.logger.error(f"Failed to navigate to {url} after {MAX_RETRIES} attempts")
                    raise

    async def delay(self, seconds: float = None):
        """Add delay between requests."""
        await asyncio.sleep(seconds or REQUEST_DELAY)

    async def safe_get_text(self, selector: str, default: str = "") -> str:
        """Safely get text content from an element."""
        try:
            element = await self.page.query_selector(selector)
            if element:
                text = await element.text_content()
                return text.strip() if text else default
            return default
        except Exception:
            return default

    # =========================================================================
    # STREET SCRAPING
    # =========================================================================

    async def scrape_all_streets(self) -> List[Dict]:
        """
        Scrape all streets from the Streets.aspx page using HTTP requests.
        
        Returns:
            List of dictionaries containing street name and URL
        """
        self.logger.info("Scraping all streets...")
        
        streets = []
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
            letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
            
            for letter in letters:
                self.logger.info(f"Scraping streets starting with '{letter}'...")
                url = f"{STREETS_URL}?Letter={letter}"
                
                try:
                    async with session.get(url, timeout=30) as response:
                        if response.status == 200:
                            html = await response.text()
                            page_streets = self._parse_streets_from_html(html)
                            streets.extend(page_streets)
                            self.logger.debug(f"Found {len(page_streets)} streets for letter {letter}")
                        else:
                            self.logger.warning(f"Failed to fetch {url}: {response.status}")
                except Exception as e:
                    self.logger.error(f"Error scraping letter {letter}: {e}")
                
                await asyncio.sleep(0.5)

        # Deduplicate
        seen = set()
        unique_streets = []
        for street in streets:
            if street['name'] not in seen:
                seen.add(street['name'])
                unique_streets.append(street)

        self.logger.info(f"Found {len(unique_streets)} unique streets total")
        return unique_streets

    def _parse_streets_from_html(self, html: str) -> List[Dict]:
        """Parse street links from HTML content."""
        streets = []
        soup = BeautifulSoup(html, 'lxml')
        
        for link in soup.find_all('a'):
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            if not href or not text:
                continue
            
            if 'Results.aspx' in href or 'Street=' in href or 'Name=' in href:
                if self._is_valid_street_name(text):
                    full_url = urljoin(BASE_URL + "/", href)
                    streets.append({
                        'name': text,
                        'url': full_url
                    })
        
        return streets

    def _is_valid_street_name(self, name: str) -> bool:
        """Check if a string looks like a valid street name."""
        if not name or len(name) < 2:
            return False
        
        exclude_patterns = [
            'next', 'previous', 'page', 'back', 'home', 'search',
            'login', 'help', 'contact', 'about', '...', '«', '»',
            'first', 'last', 'map', 'parcel'
        ]
        
        name_lower = name.lower()
        for pattern in exclude_patterns:
            if pattern in name_lower:
                return False
        
        if not any(c.isalpha() for c in name):
            return False
        
        return True

    async def save_streets_to_supabase(self, streets: List[Dict]) -> int:
        """Save scraped streets to Supabase."""
        saved_count = 0
        
        for street_data in streets:
            try:
                self.supabase.table('worcester_streets').upsert({
                    'name': street_data['name'],
                    'url': street_data['url'],
                    'scraped': False,
                    'created_at': datetime.utcnow().isoformat()
                }, on_conflict='name').execute()
                saved_count += 1
            except Exception as e:
                self.logger.debug(f"Error saving street {street_data['name']}: {e}")
        
        self.logger.info(f"Saved {saved_count} streets to Supabase")
        return saved_count

    # =========================================================================
    # PROPERTY LISTING SCRAPING
    # =========================================================================

    async def scrape_street_properties(self, street_name: str, street_url: str) -> List[Dict]:
        """
        Scrape all properties for a given street.
        
        Args:
            street_name: Name of the street
            street_url: URL to the street's property listing page
            
        Returns:
            List of property dictionaries with basic info and URLs
        """
        self.logger.info(f"Scraping properties on: {street_name}")
        
        if not street_url:
            self.logger.warning(f"No URL for street: {street_name}")
            return []
        
        await self.navigate(street_url)
        
        properties = []
        page_num = 1
        
        while True:
            page_properties = await self._extract_properties_from_page(street_name)
            properties.extend(page_properties)
            
            self.logger.debug(f"Page {page_num}: Found {len(page_properties)} properties")
            
            has_next = await self._go_to_next_page()
            if not has_next:
                break
            
            page_num += 1
            if page_num > 100:
                self.logger.warning(f"Hit pagination limit for street: {street_name}")
                break
        
        self.logger.info(f"Found {len(properties)} total properties on {street_name}")
        return properties

    async def _extract_properties_from_page(self, street_name: str) -> List[Dict]:
        """Extract property information from the current page."""
        properties = []
        
        property_selectors = [
            "#ctl00_MainContent_grdResults tr",
            "#MainContent_grdResults tr",
            "#ctl00_MainContent_grdSearchResults tr",
            "table.results tr",
            ".property-list tr",
            "table tr[onclick]",
            "table tbody tr",
        ]
        
        for selector in property_selectors:
            rows = await self.page.query_selector_all(selector)
            if rows and len(rows) > 1:
                for row in rows:
                    try:
                        property_data = await self._extract_property_from_row(row, street_name)
                        if property_data:
                            properties.append(property_data)
                    except Exception as e:
                        self.logger.debug(f"Error extracting property from row: {e}")
                        continue
                
                if properties:
                    break
        
        if not properties:
            properties = await self._extract_properties_from_links(street_name)
        
        return properties

    async def _extract_property_from_row(self, row, street_name: str) -> Optional[Dict]:
        """Extract property data from a table row element."""
        link = await row.query_selector("a[href*='Parcel']")
        if not link:
            link = await row.query_selector("a[href*='parcel']")
        if not link:
            link = await row.query_selector("a")
        
        if not link:
            return None
        
        href = await link.get_attribute('href')
        if not href:
            return None
        
        parcel_id = self._extract_parcel_id(href)
        if not parcel_id:
            return None
        
        address = await link.text_content()
        if address:
            address = address.strip()
        
        cells = await row.query_selector_all("td")
        cell_texts = []
        for cell in cells:
            text = await cell.text_content()
            if text:
                cell_texts.append(text.strip())
        
        property_data = {
            'parcel_id': parcel_id,
            'address': address,
            'street_name': street_name,
            'detail_url': urljoin(BASE_URL + "/", href),
        }
        
        if len(cell_texts) > 1:
            property_data['owner_name'] = cell_texts[1] if len(cell_texts) > 1 else None
        
        return property_data

    async def _extract_properties_from_links(self, street_name: str) -> List[Dict]:
        """Extract properties by finding all parcel links on the page."""
        properties = []
        
        link_selectors = [
            "a[href*='Parcel.aspx']",
            "a[href*='parcel.aspx']",
            "a[href*='PID=']",
            "a[href*='pid=']",
            "a[href*='ParcelID=']",
        ]
        
        for selector in link_selectors:
            links = await self.page.query_selector_all(selector)
            if links:
                for link in links:
                    try:
                        href = await link.get_attribute('href')
                        text = await link.text_content()
                        
                        if href:
                            parcel_id = self._extract_parcel_id(href)
                            if parcel_id:
                                properties.append({
                                    'parcel_id': parcel_id,
                                    'address': text.strip() if text else None,
                                    'street_name': street_name,
                                    'detail_url': urljoin(BASE_URL + "/", href)
                                })
                    except Exception as e:
                        self.logger.debug(f"Error extracting property link: {e}")
                        continue
                
                if properties:
                    break
        
        # Deduplicate
        seen = set()
        unique_properties = []
        for prop in properties:
            if prop['parcel_id'] not in seen:
                seen.add(prop['parcel_id'])
                unique_properties.append(prop)
        
        return unique_properties

    def _extract_parcel_id(self, url: str) -> Optional[str]:
        """Extract parcel ID from URL."""
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            
            for param_name in ['PID', 'pid', 'ParcelID', 'parcelid', 'id', 'ID']:
                if param_name in params:
                    return params[param_name][0]
            
            if 'pid=' in url.lower():
                match = re.search(r'pid=(\d+)', url, re.IGNORECASE)
                if match:
                    return match.group(1)
            
            return None
        except Exception:
            return None

    async def _go_to_next_page(self) -> bool:
        """Try to navigate to the next page of property results."""
        next_selectors = [
            "a:text('Next')",
            "a:text('>')",
            "a:text('>>')",
            ".next-page",
            "a[href*='Page$Next']",
            "#ctl00_MainContent_lnkNext",
        ]
        
        for selector in next_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    is_disabled = await element.get_attribute('disabled')
                    if is_disabled:
                        continue
                    
                    await element.click()
                    await self.page.wait_for_load_state('networkidle')
                    await self.delay()
                    return True
            except Exception:
                continue
        
        return False

    # =========================================================================
    # PROPERTY DETAIL SCRAPING
    # =========================================================================

    async def scrape_property_details(self, parcel_id: str, detail_url: str, street_name: str) -> Dict:
        """
        Scrape all details for a property and save to Supabase.
        
        Args:
            parcel_id: Property parcel ID
            detail_url: URL to the property detail page
            street_name: Name of the street
            
        Returns:
            Dictionary of all scraped property details
        """
        self.logger.debug(f"Scraping details for parcel: {parcel_id}")
        
        await self.navigate(detail_url)
        
        data = {
            'pid': parcel_id,
            'url': detail_url,
            'street_name': street_name,
            'scraped_at': datetime.now().isoformat()
        }
        
        # Scrape all sections
        data['basic_info'] = await self._scrape_basic_info()
        data['owner_info'] = await self._scrape_owner_info()
        data['current_sale'] = await self._scrape_current_sale()
        data['assessment'] = await self._scrape_assessment()
        data['buildings'] = await self._scrape_buildings()
        data['land_info'] = await self._scrape_land_info()
        data['sales_history'] = await self._scrape_sales_history()
        data['valuation_history'] = await self._scrape_valuation_history()
        data['extra_features'] = await self._scrape_extra_features()
        data['outbuildings'] = await self._scrape_outbuildings()
        data['permits'] = await self._scrape_permits()
        data['tax_info'] = await self._scrape_tax_info()
        data['exemptions'] = await self._scrape_exemptions()
        
        # Collect photos and layouts from buildings
        data['photos'] = []
        data['layouts'] = []
        for bldg in data.get('buildings', []):
            data['photos'].extend(bldg.get('photos', []))
            data['layouts'].extend(bldg.get('layouts', []))
        
        # Add any additional photos
        additional_photos = await self._scrape_additional_photos(
            existing_urls=set(p['url'] for p in data['photos'])
        )
        data['photos'].extend(additional_photos)
        
        # Save to Supabase
        self._save_property_to_supabase(data)
        
        return data

    async def _scrape_basic_info(self) -> Dict:
        """Extract basic property information."""
        raw_location = await self.safe_get_text("#MainContent_lblLocation")
        return {
            'location': self._format_address(raw_location),
            'mblu': await self.safe_get_text("#MainContent_lblMblu"),
            'acct_number': await self.safe_get_text("#MainContent_lblAcctNum"),
            'building_count': await self.safe_get_text("#MainContent_lblBldCount"),
            'parcel_id_display': await self.safe_get_text("#MainContent_lblPid"),
        }

    async def _scrape_owner_info(self) -> Dict:
        """Extract owner information."""
        raw_mailing = await self.safe_get_text("#MainContent_lblAddr1")
        raw_city_state = await self.safe_get_text("#MainContent_lblAddr2")
        
        owner_info = {
            'name': await self.safe_get_text("#MainContent_lblOwner") or 
                    await self.safe_get_text("#MainContent_lblGenOwner"),
            'co_owner': await self.safe_get_text("#MainContent_lblCoOwner"),
            'mailing_address': self._format_address(raw_mailing),
            'mailing_city_state_zip': raw_city_state,
        }
        
        addr_lines = []
        for i in range(1, 5):
            addr = await self.safe_get_text(f"#MainContent_lblAddr{i}")
            if addr:
                addr_lines.append(self._format_address(addr))
        if addr_lines:
            owner_info['full_mailing_address'] = ', '.join(addr_lines)
        
        return owner_info

    def _format_address(self, address: str) -> str:
        """
        Format address by properly separating street from city/state/zip.
        
        Handles cases like:
        - "120 A BROOKS STWORCESTER, MA 01606" -> "120 A BROOKS ST, WORCESTER, MA 01606"
        - "158A APRICOT STUNIT 1WORCESTER, MA 01603" -> "158A APRICOT ST UNIT 1, WORCESTER, MA 01603"
        - "12 PARK STWEBSTER, MA 01570" -> "12 PARK ST, WEBSTER, MA 01570"
        - "455 MAIN ST4TH FLOOR, WORCESTER, MA 01608" -> "455 MAIN ST 4TH FLOOR, WORCESTER, MA 01608"
        """
        if not address:
            return address
        
        # ALWAYS handle UNIT/APT/FLOOR/ordinal concatenation first (even for already-formatted addresses)
        # "STUNIT" -> "ST UNIT", "ST4TH" -> "ST 4TH", "STFLOOR" -> "ST FLOOR"
        address = re.sub(r'(ST|AVE|RD|DR|LN|CT|PL|WAY|CIR|BLVD|LANE)(\d+(?:ST|ND|RD|TH)|UNIT|APT|FLOOR|#\d)', r'\1 \2', address, flags=re.IGNORECASE)
        
        # Skip city/state parsing if already properly formatted (has ", CITY, STATE ZIP" pattern)
        if re.search(r', [A-Z][a-zA-Z\s]+, [A-Z]{2} \d{5}', address):
            return address
        
        # US state abbreviations
        states = r'MA|CT|RI|NH|NY|FL|GA|CA|TX|PA|NJ|OH|VA|NC|SC|MD|AZ|CO|WA|ME|VT|IL|MI|IN|MO|TN|AL|KY|LA|WI|MN|OR|NV|NM|OK|KS|AR|NE|IA|WV|DE|HI|ID|MT|SD|ND|WY|AK|DC|UT'
        
        # Primary approach: Look for space + street suffix + city name (no space between suffix and city)
        # Pattern: space + SUFFIX + CITY + STATE + ZIP
        # Example: " STWEBSTER, MA 01570" -> " ST, WEBSTER, MA 01570"
        # The space before suffix ensures we match complete suffixes, not substrings like "STER" in "WORCESTER"
        
        suffix_city_pattern = rf'(\s)(ST|AVE|RD|DR|LN|CT|PL|WAY|CIR|BLVD|LANE|PATH|TER|PKWY|HWY|HILL)([A-Z][A-Za-z]+),?\s*({states})\s*(\d{{5}}(?:-\d{{4}})?)'
        
        def fix_suffix_city(match):
            space = match.group(1)
            suffix = match.group(2).upper()
            city = match.group(3).strip()
            state = match.group(4).upper()
            zip_code = match.group(5)
            return f"{space}{suffix}, {city}, {state} {zip_code}"
        
        address = re.sub(suffix_city_pattern, fix_suffix_city, address, flags=re.IGNORECASE)
        
        # Secondary approach: Look for digit immediately followed by uppercase city name (no space)
        # Example: "PO BOX 723597ATLANTA, GA 31139" -> "PO BOX 723597, ATLANTA, GA 31139"
        digit_city_pattern = rf'(\d)([A-Z][A-Za-z]+),?\s*({states})\s*(\d{{5}}(?:-\d{{4}})?)'
        
        def fix_digit_city(match):
            digit = match.group(1)
            city = match.group(2).strip()
            state = match.group(3).upper()
            zip_code = match.group(4)
            return f"{digit}, {city}, {state} {zip_code}"
        
        address = re.sub(digit_city_pattern, fix_digit_city, address)
        
        return address

    async def _scrape_current_sale(self) -> Dict:
        """Extract current sale information."""
        return {
            'price': await self.safe_get_text("#MainContent_lblPrice"),
            'date': await self.safe_get_text("#MainContent_lblSaleDate"),
            'book_page': await self.safe_get_text("#MainContent_lblBp"),
            'certificate': await self.safe_get_text("#MainContent_lblCertificate"),
            'instrument': await self.safe_get_text("#MainContent_lblInstrument"),
            'deed_type': await self.safe_get_text("#MainContent_lblDeedType"),
            'grantor': await self.safe_get_text("#MainContent_lblGrantor"),
        }

    async def _scrape_assessment(self) -> Dict:
        """Extract assessment/valuation information."""
        assessment = {
            'total': await self.safe_get_text("#MainContent_lblGenAssessment")
        }
        
        assessment_rows = await self._get_table_rows("#MainContent_grdCurrentValueAsmt")
        if assessment_rows and isinstance(assessment_rows[0], dict):
            row = assessment_rows[0]
            assessment['valuation_year'] = row.get('Valuation Year')
            assessment['improvements'] = row.get('Improvements')
            assessment['land'] = row.get('Land')
            assessment['total'] = row.get('Total') or assessment['total']
        
        return assessment

    async def _scrape_buildings(self) -> List[Dict]:
        """Extract building information for all buildings on property."""
        buildings = []
        
        for bldg_idx in range(1, 10):
            bldg_prefix = f"#MainContent_ctl0{bldg_idx}"
            year_built = await self.safe_get_text(f"{bldg_prefix}_lblYearBuilt")
            
            if not year_built:
                break
            
            building = {
                'building_number': bldg_idx,
                'year_built': year_built,
                'living_area_sqft': await self.safe_get_text(f"{bldg_prefix}_lblBldArea"),
                'replacement_cost': await self.safe_get_text(f"{bldg_prefix}_lblRcn"),
                'percent_good': await self.safe_get_text(f"{bldg_prefix}_lblPctGood"),
                'rcnld': await self.safe_get_text(f"{bldg_prefix}_lblRcnld"),
                'building_value': await self.safe_get_text(f"{bldg_prefix}_lblBldgAsmt"),
                'effective_year': await self.safe_get_text(f"{bldg_prefix}_lblEffYr"),
                'depreciation': await self.safe_get_text(f"{bldg_prefix}_lblDepr"),
                'attributes': {},
                'sub_areas': [],
                'photos': [],
                'layouts': []
            }
            
            # Building attributes from table
            attr_rows = await self._get_table_rows(f"{bldg_prefix}_grdCns")
            for row in attr_rows:
                if isinstance(row, dict):
                    field = row.get('Field', '').rstrip(':').strip()
                    desc = row.get('Description', '').strip()
                    if field:
                        key = self._to_snake_case(field)
                        building['attributes'][key] = desc
            
            # Building sub-areas
            subarea_rows = await self._get_table_rows(f"{bldg_prefix}_grdSub")
            total_gross = 0
            total_living = 0
            for row in subarea_rows:
                if isinstance(row, dict):
                    gross = (row.get('Gross Area') or row.get('GrossArea') or 
                             row.get('Gross\nArea', ''))
                    living = (row.get('Living Area') or row.get('LivingArea') or 
                              row.get('Living\nArea', ''))
                    
                    gross_val = self._parse_number(gross)
                    living_val = self._parse_number(living)
                    
                    sub_area = {
                        'code': row.get('Code', '').strip(),
                        'description': row.get('Description', '').strip(),
                        'gross_area': gross_val,
                        'living_area': living_val
                    }
                    building['sub_areas'].append(sub_area)
                    
                    if gross_val:
                        total_gross += gross_val
                    if living_val:
                        total_living += living_val
            
            building['total_gross_area'] = total_gross
            building['total_living_area'] = total_living
            
            # Building photo
            photo_img = await self.page.query_selector(f"{bldg_prefix}_imgPhoto")
            if photo_img:
                src = await photo_img.get_attribute('src')
                if src and 'noimage' not in src.lower():
                    building['photos'].append({
                        'url': urljoin(self.page.url, src),
                        'photo_type': 'building',
                        'description': f'Building {bldg_idx} Photo'
                    })
            
            # Building sketch/layout
            sketch_img = await self.page.query_selector(f"{bldg_prefix}_imgSketch")
            if sketch_img:
                src = await sketch_img.get_attribute('src')
                if src and 'noimage' not in src.lower():
                    building['layouts'].append({
                        'url': urljoin(self.page.url, src),
                        'layout_type': 'sketch',
                        'description': f'Building {bldg_idx} Layout'
                    })
            
            buildings.append(building)
        
        return buildings

    async def _scrape_land_info(self) -> Dict:
        """Extract land information."""
        land_info = {
            'use_code': await self.safe_get_text("#MainContent_lblUseCode"),
            'description': await self.safe_get_text("#MainContent_lblUseCodeDescription"),
            'zone': await self.safe_get_text("#MainContent_lblZone"),
            'neighborhood': await self.safe_get_text("#MainContent_lblNbhd"),
            'size_sqft': await self.safe_get_text("#MainContent_lblLndSf"),
            'size_acres': await self.safe_get_text("#MainContent_lblLndAcres"),
            'frontage': await self.safe_get_text("#MainContent_lblFrontage"),
            'depth': await self.safe_get_text("#MainContent_lblDepth"),
            'assessed_value': await self.safe_get_text("#MainContent_lblLndAsmt"),
            'alt_land_appr': await self.safe_get_text("#MainContent_lblAltLand"),
            'category': await self.safe_get_text("#MainContent_lblCategory"),
            'land_type': await self.safe_get_text("#MainContent_lblLandType"),
            'topography': await self.safe_get_text("#MainContent_lblTopo"),
            'utilities': await self.safe_get_text("#MainContent_lblUtil"),
            'street_type': await self.safe_get_text("#MainContent_lblStreetType"),
            'traffic': await self.safe_get_text("#MainContent_lblTraffic"),
        }
        
        land_lines = await self._get_table_rows("#MainContent_grdLand")
        if land_lines:
            land_info['land_lines'] = land_lines
        
        return land_info

    async def _scrape_sales_history(self) -> List[Dict]:
        """Extract sales history."""
        return await self._get_table_rows("#MainContent_grdSales")

    async def _scrape_valuation_history(self) -> List[Dict]:
        """Extract valuation history."""
        return await self._get_table_rows("#MainContent_grdHistoryValuesAsmt")

    async def _scrape_extra_features(self) -> List[Dict]:
        """Extract extra features."""
        features = await self._get_table_rows("#MainContent_grdXf")
        return [f for f in features if not self._is_no_data_row(f)]

    async def _scrape_outbuildings(self) -> List[Dict]:
        """Extract outbuildings."""
        return await self._get_table_rows("#MainContent_grdOb")

    async def _scrape_permits(self) -> List[Dict]:
        """Extract permits."""
        return await self._get_table_rows("#MainContent_grdPermits")

    async def _scrape_exemptions(self) -> List[Dict]:
        """Extract exemptions."""
        return await self._get_table_rows("#MainContent_grdExemptions")

    async def _scrape_tax_info(self) -> Dict:
        """Extract tax information."""
        return {
            'tax_amount': await self.safe_get_text("#MainContent_lblTaxAmt"),
            'tax_year': await self.safe_get_text("#MainContent_lblTaxYear"),
            'tax_rate': await self.safe_get_text("#MainContent_lblTaxRate"),
        }

    async def _scrape_additional_photos(self, existing_urls: set) -> List[Dict]:
        """Find additional photos on the page not already captured."""
        photos = []
        try:
            all_imgs = await self.page.query_selector_all(
                "img[src*='photos'], img[src*='Photos']"
            )
            for img in all_imgs:
                src = await img.get_attribute('src')
                alt = await img.get_attribute('alt') or ''
                if src and src not in existing_urls and 'noimage' not in src.lower():
                    full_url = urljoin(self.page.url, src)
                    if full_url not in existing_urls:
                        photos.append({
                            'url': full_url,
                            'photo_type': 'additional',
                            'description': alt
                        })
        except Exception as e:
            self.logger.debug(f"Error scraping additional photos: {e}")
        return photos

    # =========================================================================
    # TABLE EXTRACTION
    # =========================================================================

    async def _get_table_rows(self, table_selector: str) -> List[Dict]:
        """Extract rows from a table as list of dicts."""
        rows = []
        try:
            table = await self.page.query_selector(table_selector)
            if not table:
                return rows
            
            header_els = await table.query_selector_all("tr.HeaderStyle th")
            if not header_els:
                header_els = await table.query_selector_all("thead tr th")
            if not header_els:
                header_els = await table.query_selector_all("tr:first-child th")
            if not header_els:
                first_row = await table.query_selector("tr:first-child")
                if first_row:
                    header_els = await first_row.query_selector_all("th, td")
            
            headers = []
            for h in header_els:
                text = await h.text_content()
                cleaned = ' '.join(text.split()) if text else ""
                headers.append(cleaned)
            
            row_els = await table.query_selector_all("tr.RowStyle, tr.AltRowStyle")
            if not row_els:
                row_els = await table.query_selector_all("tbody tr")
            if not row_els:
                all_rows = await table.query_selector_all("tr")
                row_els = all_rows[1:] if len(all_rows) > 1 else []
            
            for row_el in row_els:
                cells = await row_el.query_selector_all("td")
                if not cells:
                    continue
                
                cell_texts = []
                for cell in cells:
                    text = await cell.text_content()
                    cleaned = ' '.join(text.split()) if text else ""
                    cell_texts.append(cleaned)
                
                if not any(cell_texts):
                    continue
                
                if headers and len(cell_texts) == len(headers):
                    rows.append(dict(zip(headers, cell_texts)))
                elif cell_texts:
                    rows.append(cell_texts)
                    
        except Exception as e:
            self.logger.debug(f"Error extracting table {table_selector}: {e}")
        return rows

    # =========================================================================
    # SUPABASE SAVE METHODS
    # =========================================================================

    def _save_property_to_supabase(self, details: Dict) -> bool:
        """Save scraped property details to Supabase worcester_data_collection table."""
        try:
            buildings = details.get('buildings', [])
            first_bldg = buildings[0] if buildings else {}
            attrs = first_bldg.get('attributes', {})
            assessment = details.get('assessment', {})
            land = details.get('land_info', {})
            current_sale = details.get('current_sale', {})
            tax = details.get('tax_info', {})
            owner = details.get('owner_info', {})
            
            # Parse last sale date
            last_sale_date = None
            if current_sale.get('date'):
                try:
                    date_str = current_sale['date']
                    for fmt in ['%m/%d/%Y', '%Y-%m-%d', '%m-%d-%Y']:
                        try:
                            last_sale_date = datetime.strptime(date_str, fmt).date().isoformat()
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass
            
            record = {
                'parcel_id': details.get('pid'),
                'source_url': details.get('url'),
                'scraped_at': details.get('scraped_at'),
                'street_name': details.get('street_name'),
                'location': details.get('basic_info', {}).get('location'),
                'mblu': details.get('basic_info', {}).get('mblu'),
                'acct_number': details.get('basic_info', {}).get('acct_number'),
                'building_count': self._parse_int(details.get('basic_info', {}).get('building_count')),
                'owner_name': owner.get('name'),
                'co_owner': owner.get('co_owner'),
                'owner_mailing_address': owner.get('full_mailing_address') or owner.get('mailing_address'),
                'total_assessed_value': self._parse_currency(assessment.get('total')),
                'land_value': self._parse_currency(assessment.get('land')),
                'improvements_value': self._parse_currency(assessment.get('improvements')),
                'year_built': self._parse_int(first_bldg.get('year_built')),
                'living_area_sqft': self._parse_int(first_bldg.get('living_area_sqft')),
                'lot_size_sqft': self._parse_float(land.get('size_sqft')),
                'lot_size_acres': self._parse_float(land.get('size_acres')),
                'zoning': land.get('zone'),
                'use_code': land.get('use_code'),
                'use_description': land.get('description'),
                'neighborhood': land.get('neighborhood'),
                'bedrooms': self._parse_int(attrs.get('total_bedrooms')),
                'bathrooms': self._parse_float(attrs.get('total_full_bthrms')),
                'total_rooms': self._parse_int(attrs.get('total_rooms')),
                'building_style': attrs.get('style'),
                'exterior_wall': attrs.get('exterior_wall_1'),
                'roof_structure': attrs.get('roof_structure'),
                'heat_type': attrs.get('heat_type'),
                'ac_type': attrs.get('ac_type'),
                'last_sale_price': self._parse_currency(current_sale.get('price')),
                'last_sale_date': last_sale_date,
                'book_page': current_sale.get('book_page'),
                'tax_amount': self._parse_currency(tax.get('tax_amount')),
                'tax_year': tax.get('tax_year'),
                'tax_rate': self._parse_float(tax.get('tax_rate')),
                'buildings': buildings,
                'photos': details.get('photos', []),
                'layouts': details.get('layouts', []),
                'sales_history': details.get('sales_history', []),
                'valuation_history': details.get('valuation_history', []),
                'extra_features': details.get('extra_features', []),
                'outbuildings': details.get('outbuildings', []),
                'permits': details.get('permits', []),
                'exemptions': details.get('exemptions', []),
                'land_details': land,
                'current_sale_details': current_sale,
                'owner_details': owner,
                'raw_data': details,
            }
            
            record = {k: v for k, v in record.items() if v is not None}
            
            self.supabase.table('worcester_data_collection').upsert(
                record,
                on_conflict='parcel_id'
            ).execute()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error saving to Supabase: {e}")
            return False

    # =========================================================================
    # PROGRESS TRACKING
    # =========================================================================

    def update_progress(self, **kwargs):
        """Update scraping progress in Supabase."""
        try:
            self.supabase.table('worcester_scraping_progress').upsert({
                'task_name': 'worcester_full_scrape',
                **kwargs,
                'updated_at': datetime.utcnow().isoformat()
            }, on_conflict='task_name').execute()
        except Exception as e:
            self.logger.error(f"Error updating progress: {e}")

    def mark_street_complete(self, street_name: str, property_count: int):
        """Mark a street as fully scraped."""
        try:
            self.supabase.table('worcester_streets').update({
                'scraped': True,
                'property_count': property_count,
                'scraped_at': datetime.utcnow().isoformat()
            }).eq('name', street_name).execute()
        except Exception as e:
            self.logger.error(f"Error marking street complete: {e}")

    def get_unscraped_streets(self) -> List[Dict]:
        """Get list of streets that haven't been scraped yet."""
        try:
            result = self.supabase.table('worcester_streets').select('*').eq('scraped', False).execute()
            return result.data
        except Exception as e:
            self.logger.error(f"Error getting unscraped streets: {e}")
            return []

    def get_progress(self) -> Dict:
        """Get current scraping progress."""
        try:
            result = self.supabase.table('worcester_scraping_progress').select('*').eq(
                'task_name', 'worcester_full_scrape'
            ).single().execute()
            return result.data
        except Exception:
            return {}

    def get_stats(self) -> Dict:
        """Get scraping statistics from Supabase."""
        try:
            streets_result = self.supabase.table('worcester_streets').select('*', count='exact').execute()
            scraped_streets = self.supabase.table('worcester_streets').select('*', count='exact').eq('scraped', True).execute()
            properties_result = self.supabase.table('worcester_data_collection').select('*', count='exact').execute()
            
            return {
                'total_streets': streets_result.count or 0,
                'scraped_streets': scraped_streets.count or 0,
                'total_properties': properties_result.count or 0
            }
        except Exception as e:
            self.logger.error(f"Error getting stats: {e}")
            return {}

    # =========================================================================
    # PARSING UTILITIES
    # =========================================================================

    def _parse_number(self, value: str) -> Optional[int]:
        """Parse a numeric string."""
        if not value:
            return None
        try:
            cleaned = re.sub(r'[,$\s]', '', str(value))
            match = re.search(r'[\d.]+', cleaned)
            if match:
                num = float(match.group())
                return int(num) if num == int(num) else num
        except (ValueError, TypeError):
            pass
        return None

    def _parse_currency(self, value: str) -> Optional[float]:
        """Parse a currency string to float."""
        if not value:
            return None
        try:
            cleaned = re.sub(r'[$,\s]', '', value)
            return float(cleaned)
        except ValueError:
            return None

    def _parse_int(self, value: Any) -> Optional[int]:
        """Parse value to integer."""
        if value is None:
            return None
        try:
            return int(re.sub(r'[^\d]', '', str(value)))
        except (ValueError, TypeError):
            return None

    def _parse_float(self, value: Any) -> Optional[float]:
        """Parse value to float."""
        if value is None:
            return None
        try:
            cleaned = re.sub(r'[^\d.]', '', str(value))
            return float(cleaned) if cleaned else None
        except (ValueError, TypeError):
            return None

    def _to_snake_case(self, text: str) -> str:
        """Convert text to snake_case key."""
        cleaned = re.sub(r'[^\w\s]', '', text.lower())
        return re.sub(r'_+', '_', cleaned.replace(' ', '_')).strip('_')

    def _is_no_data_row(self, row: Any) -> bool:
        """Check if a row is a 'No Data' message."""
        if isinstance(row, dict):
            values = ' '.join(str(v).lower() for v in row.values())
            return 'no data' in values
        return False

    # =========================================================================
    # MAIN SCRAPING METHODS
    # =========================================================================

    async def scrape_street(self, street_name: str, street_url: str) -> int:
        """
        Scrape all properties for a single street.
        
        Args:
            street_name: Name of the street
            street_url: URL to the street's property listing
            
        Returns:
            Number of properties scraped
        """
        self.logger.info(f"Processing street: {street_name}")
        
        # Update progress
        self.update_progress(
            current_street=street_name,
            status='running',
            started_at=datetime.utcnow().isoformat()
        )
        
        # Get all properties on this street
        properties = await self.scrape_street_properties(street_name, street_url)
        
        # Scrape details for each property
        scraped_count = 0
        for idx, prop in enumerate(properties, 1):
            try:
                self.logger.info(f"  [{idx}/{len(properties)}] Scraping {prop.get('address', prop['parcel_id'])}")
                await self.scrape_property_details(
                    parcel_id=prop['parcel_id'],
                    detail_url=prop['detail_url'],
                    street_name=street_name
                )
                scraped_count += 1
            except Exception as e:
                self.logger.error(f"Error scraping property {prop['parcel_id']}: {e}")
                continue
        
        # Mark street as complete
        self.mark_street_complete(street_name, scraped_count)
        self.logger.info(f"Completed street {street_name}: {scraped_count} properties")
        
        return scraped_count

    async def run_full_scrape(self, resume: bool = True) -> Dict:
        """
        Run the full scraping pipeline.
        
        Args:
            resume: If True, skip already scraped streets
            
        Returns:
            Dictionary with scraping statistics
        """
        self.logger.info("=" * 60)
        self.logger.info("Starting Worcester Property Scraping (Supabase-only)")
        self.logger.info("=" * 60)
        
        start_time = datetime.utcnow()
        
        # Stage 1: Scrape and save all streets
        self.logger.info("\n[Stage 1] Fetching street list...")
        streets = await self.scrape_all_streets()
        await self.save_streets_to_supabase(streets)
        
        total_streets = len(streets)
        self.update_progress(
            total_streets=total_streets,
            status='running',
            started_at=start_time.isoformat()
        )
        
        # Stage 2: Process each unscraped street
        if resume:
            streets_to_process = self.get_unscraped_streets()
        else:
            streets_to_process = [{'name': s['name'], 'url': s['url']} for s in streets]
        
        self.logger.info(f"\n[Stage 2] Processing {len(streets_to_process)} streets...")
        
        total_properties = 0
        completed_streets = 0
        
        for idx, street in enumerate(streets_to_process, 1):
            self.logger.info(f"\n--- Street {idx}/{len(streets_to_process)}: {street['name']} ---")
            
            try:
                prop_count = await self.scrape_street(street['name'], street['url'])
                total_properties += prop_count
                completed_streets += 1
                
                # Update progress
                self.update_progress(
                    completed_streets=completed_streets,
                    completed_properties=total_properties
                )
                
            except Exception as e:
                self.logger.error(f"Error processing street {street['name']}: {e}")
                continue
        
        # Finalize
        elapsed = datetime.utcnow() - start_time
        self.update_progress(
            status='completed',
            completed_at=datetime.utcnow().isoformat()
        )
        
        self.logger.info("\n" + "=" * 60)
        self.logger.info(f"Scraping completed in {elapsed}")
        self.logger.info(f"Streets: {completed_streets}/{len(streets_to_process)}")
        self.logger.info(f"Properties: {total_properties}")
        self.logger.info("=" * 60)
        
        return {
            'elapsed': str(elapsed),
            'streets_scraped': completed_streets,
            'properties_scraped': total_properties
        }

