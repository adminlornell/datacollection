"""
Base scraper class with common functionality.
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional
from playwright.async_api import async_playwright, Browser, Page, BrowserContext

from ..config import (
    BASE_URL, HEADLESS, SLOW_MO, TIMEOUT, USER_AGENT,
    REQUEST_DELAY, MAX_RETRIES
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


class BaseScraper:
    """Base class for all scrapers with common browser management."""

    def __init__(self, db_session):
        self.db_session = db_session
        self.logger = logging.getLogger(self.__class__.__name__)
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
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    self.logger.error(f"Failed to navigate to {url} after {MAX_RETRIES} attempts")
                    raise

    async def delay(self, seconds: float = None):
        """Add delay between requests to be respectful to the server."""
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

    async def safe_get_attribute(self, selector: str, attribute: str, default: str = "") -> str:
        """Safely get an attribute from an element."""
        try:
            element = await self.page.query_selector(selector)
            if element:
                value = await element.get_attribute(attribute)
                return value if value else default
            return default
        except Exception:
            return default

    async def wait_for_element(self, selector: str, timeout: int = None) -> bool:
        """Wait for an element to appear."""
        try:
            await self.page.wait_for_selector(selector, timeout=timeout or TIMEOUT)
            return True
        except Exception:
            return False

    async def get_all_elements(self, selector: str) -> list:
        """Get all elements matching a selector."""
        return await self.page.query_selector_all(selector)

    async def screenshot(self, path: str):
        """Take a screenshot for debugging."""
        await self.page.screenshot(path=path)
        self.logger.info(f"Screenshot saved: {path}")
