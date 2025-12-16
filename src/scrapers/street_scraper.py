"""
Scraper for extracting all street names from the Worcester MA GIS site.
"""
import asyncio
import aiohttp
import ssl
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict
from urllib.parse import urljoin

from .base_scraper import BaseScraper
from ..config import STREETS_URL, BASE_URL
from ..models import Street, ScrapingProgress


class StreetScraper(BaseScraper):
    """
    Scrapes all street names from the Streets.aspx page using HTTP requests (faster/reliable).
    """

    async def scrape_all_streets(self) -> List[Dict]:
        """
        Scrape all streets from the Streets.aspx page.

        Returns:
            List of dictionaries containing street name and URL
        """
        self.logger.info("Starting street scraping (HTTP mode)...")

        streets = []
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
            # Scrape alphabetically A-Z
            letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
            for letter in letters:
                self.logger.info(f"Scraping streets starting with '{letter}'...")

                # Try Letter=X pattern which was confirmed to work
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

                await asyncio.sleep(0.5)  # Be respectful

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

        # Look for links that contain 'Results.aspx' or 'Street=' or 'Streets.aspx?Name='
        # This matches what we found working in the scrape_wachusett_http.py script
        for link in soup.find_all('a'):
            href = link.get('href', '')
            text = link.get_text(strip=True)

            if not href or not text:
                continue

            if 'Results.aspx' in href or 'Street=' in href or 'Name=' in href:
                # Check if it looks like a valid street name
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

        # Exclude common non-street links
        exclude_patterns = [
            'next', 'previous', 'page', 'back', 'home', 'search',
            'login', 'help', 'contact', 'about', '...', '«', '»',
            'first', 'last', 'map', 'parcel'
        ]

        name_lower = name.lower()
        for pattern in exclude_patterns:
            if pattern in name_lower:
                return False

        # Must contain at least one letter
        if not any(c.isalpha() for c in name):
            return False

        return True

    async def save_streets_to_db(self, streets: List[Dict]) -> int:
        """Save scraped streets to database."""
        saved_count = 0

        for street_data in streets:
            # Check if street already exists
            existing = self.db_session.query(Street).filter_by(
                name=street_data['name']
            ).first()

            if not existing:
                street = Street(
                    name=street_data['name'],
                    url=street_data['url'],
                    created_at=datetime.utcnow()
                )
                self.db_session.add(street)
                saved_count += 1

        self.db_session.commit()
        self.logger.info(f"Saved {saved_count} new streets to database")
        return saved_count

    async def run(self) -> int:
        """Main entry point - scrape all streets and save to database."""
        # Update progress
        progress = self.db_session.query(ScrapingProgress).filter_by(
            task_name='streets'
        ).first()

        if not progress:
            progress = ScrapingProgress(
                task_name='streets',
                status='in_progress',
                started_at=datetime.utcnow()
            )
            self.db_session.add(progress)
            self.db_session.commit()

        try:
            streets = await self.scrape_all_streets()
            saved = await self.save_streets_to_db(streets)

            progress.status = 'completed'
            progress.total_items = len(streets)
            progress.completed_items = saved
            progress.completed_at = datetime.utcnow()
            self.db_session.commit()

            return len(streets)

        except Exception as e:
            progress.status = 'failed'
            progress.error_message = str(e)
            self.db_session.commit()
            raise
