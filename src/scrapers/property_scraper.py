"""
Scraper for extracting property listings from each street page.
"""
import asyncio
import re
from datetime import datetime
from typing import List, Dict, Optional
from urllib.parse import urljoin, parse_qs, urlparse

from .base_scraper import BaseScraper
from ..config import BASE_URL
from ..models import Street, Property, ScrapingProgress


class PropertyScraper(BaseScraper):
    """
    Scrapes property listings from street pages.

    For each street, navigates to its page and extracts all property
    listings with their basic info and detail page URLs.
    """

    async def scrape_street_properties(self, street: Street) -> List[Dict]:
        """
        Scrape all properties for a given street.

        Args:
            street: Street model object with URL

        Returns:
            List of property dictionaries with basic info and URLs
        """
        self.logger.info(f"Scraping properties on: {street.name}")

        if not street.url:
            self.logger.warning(f"No URL for street: {street.name}")
            return []

        await self.navigate(street.url)

        properties = []
        page_num = 1

        while True:
            # Extract properties from current page
            page_properties = await self._extract_properties_from_page(street)
            properties.extend(page_properties)

            self.logger.debug(f"Page {page_num}: Found {len(page_properties)} properties")

            # Try to go to next page
            has_next = await self._go_to_next_page()
            if not has_next:
                break

            page_num += 1
            if page_num > 100:  # Safety limit
                self.logger.warning(f"Hit pagination limit for street: {street.name}")
                break

        self.logger.info(f"Found {len(properties)} total properties on {street.name}")
        return properties

    async def _extract_properties_from_page(self, street: Street) -> List[Dict]:
        """Extract property information from the current page."""
        properties = []

        # Common selectors for property listings on VGSI sites
        property_selectors = [
            # GridView patterns (ASP.NET)
            "#ctl00_MainContent_grdResults tr",
            "#MainContent_grdResults tr",
            "#ctl00_MainContent_grdSearchResults tr",
            "table.results tr",
            ".property-list tr",
            # Generic table rows
            "table tr[onclick]",
            "table tbody tr",
        ]

        for selector in property_selectors:
            rows = await self.get_all_elements(selector)
            if rows and len(rows) > 1:  # More than just header row
                self.logger.debug(f"Found {len(rows)} rows with selector: {selector}")

                for row in rows:
                    try:
                        property_data = await self._extract_property_from_row(row, street)
                        if property_data:
                            properties.append(property_data)
                    except Exception as e:
                        self.logger.debug(f"Error extracting property from row: {e}")
                        continue

                if properties:
                    break  # Found properties with this selector

        # Also try link-based extraction if table approach didn't work
        if not properties:
            properties = await self._extract_properties_from_links(street)

        return properties

    async def _extract_property_from_row(self, row, street: Street) -> Optional[Dict]:
        """Extract property data from a table row element."""
        # Try to find the detail link
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

        # Extract parcel ID from URL
        parcel_id = self._extract_parcel_id(href)
        if not parcel_id:
            return None

        # Get address/location from link text or row cells
        address = await link.text_content()
        if address:
            address = address.strip()

        # Try to get additional info from row cells
        cells = await row.query_selector_all("td")
        cell_texts = []
        for cell in cells:
            text = await cell.text_content()
            if text:
                cell_texts.append(text.strip())

        # Build property data
        property_data = {
            'parcel_id': parcel_id,
            'address': address,
            'street_id': street.id,
            'detail_url': urljoin(BASE_URL + "/", href),
            'raw_data': cell_texts  # Store raw cell data for later processing
        }

        # Try to extract owner name if visible
        if len(cell_texts) > 1:
            # Common patterns: Address, Owner, Location, Value, etc.
            property_data['owner_name'] = cell_texts[1] if len(cell_texts) > 1 else None

        return property_data

    async def _extract_properties_from_links(self, street: Street) -> List[Dict]:
        """Extract properties by finding all parcel links on the page."""
        properties = []

        # Look for all parcel links
        link_selectors = [
            "a[href*='Parcel.aspx']",
            "a[href*='parcel.aspx']",
            "a[href*='PID=']",
            "a[href*='pid=']",
            "a[href*='ParcelID=']",
        ]

        for selector in link_selectors:
            links = await self.get_all_elements(selector)
            if links:
                self.logger.debug(f"Found {len(links)} parcel links with selector: {selector}")

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
                                    'street_id': street.id,
                                    'detail_url': urljoin(BASE_URL + "/", href)
                                })
                    except Exception as e:
                        self.logger.debug(f"Error extracting property link: {e}")
                        continue

                if properties:
                    break

        # Deduplicate by parcel_id
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

            # Try common parameter names
            for param_name in ['PID', 'pid', 'ParcelID', 'parcelid', 'id', 'ID']:
                if param_name in params:
                    return params[param_name][0]

            # Fallback for paths like /Parcel.aspx?pid=123
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
                    # Check if element is enabled/visible
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

    async def save_properties_to_db(self, properties: List[Dict], street: Street) -> int:
        """Save scraped properties to database."""
        saved_count = 0

        for prop_data in properties:
            # Check if property already exists
            existing = self.db_session.query(Property).filter_by(
                parcel_id=prop_data['parcel_id']
            ).first()

            if not existing:
                property_obj = Property(
                    parcel_id=prop_data['parcel_id'],
                    address=prop_data.get('address'),
                    street_id=street.id,
                    detail_url=prop_data.get('detail_url'),
                    owner_name=prop_data.get('owner_name'),
                    created_at=datetime.utcnow()
                )
                self.db_session.add(property_obj)
                saved_count += 1
            else:
                # Update existing
                if prop_data.get('address'):
                    existing.address = prop_data.get('address')
                if prop_data.get('owner_name'):
                    existing.owner_name = prop_data.get('owner_name')

        # Update street metadata
        street.property_count = len(properties)
        street.scraped = True
        street.scraped_at = datetime.utcnow()

        self.db_session.commit()
        self.logger.info(f"Saved {saved_count} new properties for {street.name}")
        return saved_count

    async def scrape_all_streets(self, resume: bool = True) -> int:
        """
        Scrape properties for all streets in the database.

        Args:
            resume: If True, skip already scraped streets

        Returns:
            Total number of properties found
        """
        # Get streets to scrape
        query = self.db_session.query(Street)
        if resume:
            query = query.filter_by(scraped=False)

        streets = query.all()
        total_streets = len(streets)

        if total_streets == 0:
            self.logger.info("No streets to scrape")
            return 0

        self.logger.info(f"Scraping properties for {total_streets} streets")

        total_properties = 0

        for idx, street in enumerate(streets, 1):
            self.logger.info(f"Progress: {idx}/{total_streets} - {street.name}")

            try:
                properties = await self.scrape_street_properties(street)
                await self.save_properties_to_db(properties, street)
                total_properties += len(properties)

            except Exception as e:
                self.logger.error(f"Error scraping {street.name}: {e}")
                continue

        self.logger.info(f"Completed scraping. Total properties: {total_properties}")
        return total_properties

    async def run(self, resume: bool = True) -> int:
        """Main entry point."""
        return await self.scrape_all_streets(resume=resume)
