"""
Scraper for extracting all street names from the Worcester MA GIS site.
"""
import asyncio
from datetime import datetime
from typing import List, Dict
from urllib.parse import urljoin

from .base_scraper import BaseScraper
from ..config import STREETS_URL, BASE_URL
from ..models import Street, ScrapingProgress


class StreetScraper(BaseScraper):
    """
    Scrapes all street names from the Streets.aspx page.

    The VGSI Streets.aspx page typically displays streets in an alphabetical
    list with links to view properties on each street.
    """

    async def scrape_all_streets(self) -> List[Dict]:
        """
        Scrape all streets from the Streets.aspx page.

        Returns:
            List of dictionaries containing street name and URL
        """
        self.logger.info("Starting street scraping...")

        # Navigate to streets page
        await self.navigate(STREETS_URL)

        # Check for alphabetical navigation (A-Z links)
        has_alpha_nav = await self._check_alphabetical_navigation()

        streets = []
        if has_alpha_nav:
            streets = await self._scrape_alphabetically()
        else:
            streets = await self._scrape_single_page()

        self.logger.info(f"Found {len(streets)} streets")
        return streets

    async def _check_alphabetical_navigation(self) -> bool:
        """Check if the page has A-Z alphabetical navigation."""
        # Look for common alphabetical navigation patterns
        alpha_selectors = [
            "a[href*='letter=']",
            ".alpha-nav a",
            "#alphaNav a",
            "a.letter-link"
        ]

        for selector in alpha_selectors:
            elements = await self.get_all_elements(selector)
            if len(elements) > 5:  # At least some letters present
                return True

        return False

    async def _scrape_alphabetically(self) -> List[Dict]:
        """Scrape streets by navigating through A-Z pages."""
        streets = []
        letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'

        for letter in letters:
            self.logger.info(f"Scraping streets starting with '{letter}'...")

            # Try different URL patterns for alphabetical navigation
            letter_urls = [
                f"{STREETS_URL}?letter={letter}",
                f"{STREETS_URL}?Letter={letter}",
                f"{STREETS_URL}?alpha={letter}",
            ]

            for url in letter_urls:
                try:
                    await self.navigate(url)
                    page_streets = await self._extract_streets_from_page()
                    if page_streets:
                        streets.extend(page_streets)
                        break
                except Exception as e:
                    self.logger.debug(f"Letter URL pattern failed: {url} - {e}")
                    continue

            await self.delay(0.5)  # Brief delay between letters

        return streets

    async def _scrape_single_page(self) -> List[Dict]:
        """Scrape all streets from a single page (or paginated pages)."""
        streets = []

        # First, get streets from current page
        page_streets = await self._extract_streets_from_page()
        streets.extend(page_streets)

        # Check for pagination
        page_num = 2
        while True:
            has_next = await self._go_to_next_page(page_num)
            if not has_next:
                break

            page_streets = await self._extract_streets_from_page()
            if not page_streets:
                break

            streets.extend(page_streets)
            page_num += 1
            self.logger.info(f"Scraped page {page_num - 1}, total streets: {len(streets)}")

        return streets

    async def _extract_streets_from_page(self) -> List[Dict]:
        """Extract street links from the current page."""
        streets = []

        # Common selectors for street links on VGSI sites
        street_selectors = [
            # Table-based layouts
            "table a[href*='Street']",
            "table a[href*='street']",
            "table.grid a",
            "#ctl00_MainContent_grdStreets a",
            "#MainContent_grdStreets a",
            ".street-list a",
            # List-based layouts
            "ul.streets a",
            ".street-item a",
            # Generic data grid
            "[id*='Street'] a",
            "[id*='grid'] a[href]",
            # ASP.NET GridView patterns
            "tr td a[href*='aspx']",
        ]

        for selector in street_selectors:
            elements = await self.get_all_elements(selector)
            if elements:
                self.logger.debug(f"Found {len(elements)} elements with selector: {selector}")

                for element in elements:
                    try:
                        name = await element.text_content()
                        href = await element.get_attribute('href')

                        if name and href:
                            name = name.strip()
                            # Filter out non-street links
                            if self._is_valid_street_name(name):
                                full_url = urljoin(BASE_URL + "/", href)
                                streets.append({
                                    'name': name,
                                    'url': full_url
                                })
                    except Exception as e:
                        self.logger.debug(f"Error extracting street: {e}")
                        continue

                if streets:
                    break  # Found streets with this selector

        # Deduplicate by street name
        seen = set()
        unique_streets = []
        for street in streets:
            if street['name'] not in seen:
                seen.add(street['name'])
                unique_streets.append(street)

        return unique_streets

    def _is_valid_street_name(self, name: str) -> bool:
        """Check if a string looks like a valid street name."""
        if not name or len(name) < 2:
            return False

        # Exclude common non-street links
        exclude_patterns = [
            'next', 'previous', 'page', 'back', 'home', 'search',
            'login', 'help', 'contact', 'about', '...', '«', '»',
            'first', 'last'
        ]

        name_lower = name.lower()
        for pattern in exclude_patterns:
            if pattern in name_lower:
                return False

        # Must contain at least one letter
        if not any(c.isalpha() for c in name):
            return False

        return True

    async def _go_to_next_page(self, page_num: int) -> bool:
        """Try to navigate to the next page of results."""
        # Common pagination patterns
        next_selectors = [
            f"a[href*='page={page_num}']",
            f"a[href*='Page={page_num}']",
            f"a:text('{page_num}')",
            "a:text('Next')",
            "a:text('>')",
            ".pagination a.next",
            "#next-page",
        ]

        for selector in next_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    await element.click()
                    await self.page.wait_for_load_state('networkidle')
                    await self.delay()
                    return True
            except Exception:
                continue

        return False

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
