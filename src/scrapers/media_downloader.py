"""
Asynchronous media downloader for property photos and layouts.
"""
import asyncio
import aiohttp
import aiofiles
import os
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse, unquote

from ..config import PHOTOS_DIR, LAYOUTS_DIR, MAX_CONCURRENT_DOWNLOADS, USER_AGENT
from ..models import Property, PropertyPhoto, PropertyLayout

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


class MediaDownloader:
    """
    Downloads property photos and layouts asynchronously.

    Features:
    - Concurrent downloads with rate limiting
    - Resume capability (skips already downloaded files)
    - Organized folder structure by property ID
    - Error tracking and retry logic
    """

    def __init__(self, db_session):
        self.db_session = db_session
        self.logger = logging.getLogger(self.__class__.__name__)
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
        self.headers = {
            'User-Agent': USER_AGENT,
            'Accept': 'image/*,*/*',
        }

    async def download_all_media(self, resume: bool = True) -> dict:
        """
        Download all photos and layouts for all properties.

        Args:
            resume: If True, skip already downloaded files

        Returns:
            Dictionary with download statistics
        """
        stats = {
            'photos_downloaded': 0,
            'photos_failed': 0,
            'layouts_downloaded': 0,
            'layouts_failed': 0,
        }

        # Download photos
        self.logger.info("Starting photo downloads...")
        photo_stats = await self._download_all_photos(resume)
        stats['photos_downloaded'] = photo_stats['success']
        stats['photos_failed'] = photo_stats['failed']

        # Download layouts
        self.logger.info("Starting layout downloads...")
        layout_stats = await self._download_all_layouts(resume)
        stats['layouts_downloaded'] = layout_stats['success']
        stats['layouts_failed'] = layout_stats['failed']

        self.logger.info(f"Download complete: {stats}")
        return stats

    async def _download_all_photos(self, resume: bool = True) -> dict:
        """Download all property photos."""
        query = self.db_session.query(PropertyPhoto)
        if resume:
            query = query.filter_by(downloaded=False)

        photos = query.all()
        total = len(photos)

        if total == 0:
            self.logger.info("No photos to download")
            return {'success': 0, 'failed': 0}

        self.logger.info(f"Downloading {total} photos...")

        success = 0
        failed = 0

        async with aiohttp.ClientSession(headers=self.headers) as session:
            tasks = []
            for photo in photos:
                task = self._download_photo(session, photo)
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if result is True:
                    success += 1
                else:
                    failed += 1

        return {'success': success, 'failed': failed}

    async def _download_all_layouts(self, resume: bool = True) -> dict:
        """Download all property layouts."""
        query = self.db_session.query(PropertyLayout)
        if resume:
            query = query.filter_by(downloaded=False)

        layouts = query.all()
        total = len(layouts)

        if total == 0:
            self.logger.info("No layouts to download")
            return {'success': 0, 'failed': 0}

        self.logger.info(f"Downloading {total} layouts...")

        success = 0
        failed = 0

        async with aiohttp.ClientSession(headers=self.headers) as session:
            tasks = []
            for layout in layouts:
                task = self._download_layout(session, layout)
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if result is True:
                    success += 1
                else:
                    failed += 1

        return {'success': success, 'failed': failed}

    async def _download_photo(self, session: aiohttp.ClientSession, photo: PropertyPhoto) -> bool:
        """Download a single photo."""
        async with self.semaphore:
            try:
                # Get property for folder organization
                property_obj = self.db_session.query(Property).get(photo.property_id)
                if not property_obj:
                    self.logger.warning(f"Property not found for photo {photo.id}")
                    return False

                # Create property folder
                property_folder = PHOTOS_DIR / self._sanitize_folder_name(
                    property_obj.parcel_id or str(property_obj.id)
                )
                property_folder.mkdir(parents=True, exist_ok=True)

                # Generate filename
                filename = self._generate_filename(photo.url, photo.photo_type or 'photo', photo.id)
                file_path = property_folder / filename

                # Skip if already exists
                if file_path.exists():
                    photo.local_path = str(file_path)
                    photo.filename = filename
                    photo.downloaded = True
                    self.db_session.commit()
                    return True

                # Download
                async with session.get(photo.url, timeout=30) as response:
                    if response.status == 200:
                        content = await response.read()

                        async with aiofiles.open(file_path, 'wb') as f:
                            await f.write(content)

                        photo.local_path = str(file_path)
                        photo.filename = filename
                        photo.downloaded = True
                        photo.download_error = None
                        self.db_session.commit()

                        self.logger.debug(f"Downloaded photo: {filename}")
                        return True
                    else:
                        photo.download_error = f"HTTP {response.status}"
                        self.db_session.commit()
                        self.logger.warning(f"Failed to download photo {photo.id}: HTTP {response.status}")
                        return False

            except asyncio.TimeoutError:
                photo.download_error = "Timeout"
                self.db_session.commit()
                self.logger.warning(f"Timeout downloading photo {photo.id}")
                return False
            except Exception as e:
                photo.download_error = str(e)[:500]
                self.db_session.commit()
                self.logger.error(f"Error downloading photo {photo.id}: {e}")
                return False

    async def _download_layout(self, session: aiohttp.ClientSession, layout: PropertyLayout) -> bool:
        """Download a single layout/sketch."""
        async with self.semaphore:
            try:
                # Get property for folder organization
                property_obj = self.db_session.query(Property).get(layout.property_id)
                if not property_obj:
                    self.logger.warning(f"Property not found for layout {layout.id}")
                    return False

                # Create property folder
                property_folder = LAYOUTS_DIR / self._sanitize_folder_name(
                    property_obj.parcel_id or str(property_obj.id)
                )
                property_folder.mkdir(parents=True, exist_ok=True)

                # Generate filename
                filename = self._generate_filename(layout.url, layout.layout_type or 'layout', layout.id)
                file_path = property_folder / filename

                # Skip if already exists
                if file_path.exists():
                    layout.local_path = str(file_path)
                    layout.filename = filename
                    layout.downloaded = True
                    self.db_session.commit()
                    return True

                # Download
                async with session.get(layout.url, timeout=30) as response:
                    if response.status == 200:
                        content = await response.read()

                        async with aiofiles.open(file_path, 'wb') as f:
                            await f.write(content)

                        layout.local_path = str(file_path)
                        layout.filename = filename
                        layout.downloaded = True
                        layout.download_error = None
                        self.db_session.commit()

                        self.logger.debug(f"Downloaded layout: {filename}")
                        return True
                    else:
                        layout.download_error = f"HTTP {response.status}"
                        self.db_session.commit()
                        self.logger.warning(f"Failed to download layout {layout.id}: HTTP {response.status}")
                        return False

            except asyncio.TimeoutError:
                layout.download_error = "Timeout"
                self.db_session.commit()
                self.logger.warning(f"Timeout downloading layout {layout.id}")
                return False
            except Exception as e:
                layout.download_error = str(e)[:500]
                self.db_session.commit()
                self.logger.error(f"Error downloading layout {layout.id}: {e}")
                return False

    def _sanitize_folder_name(self, name: str) -> str:
        """Sanitize a string for use as a folder name."""
        # Replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '_')
        return name.strip()

    def _generate_filename(self, url: str, prefix: str, item_id: int) -> str:
        """Generate a unique filename for a downloaded file."""
        # Try to extract extension from URL
        parsed = urlparse(url)
        path = unquote(parsed.path)
        ext = os.path.splitext(path)[1].lower()

        # Default to .jpg if no extension
        if not ext or ext not in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']:
            ext = '.jpg'

        # Create unique filename
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        filename = f"{prefix}_{item_id}_{url_hash}{ext}"

        return filename

    async def download_property_media(self, property_id: int) -> dict:
        """
        Download all media for a specific property.

        Args:
            property_id: ID of the property

        Returns:
            Dictionary with download statistics
        """
        stats = {'photos': 0, 'layouts': 0, 'failed': 0}

        photos = self.db_session.query(PropertyPhoto).filter_by(
            property_id=property_id,
            downloaded=False
        ).all()

        layouts = self.db_session.query(PropertyLayout).filter_by(
            property_id=property_id,
            downloaded=False
        ).all()

        async with aiohttp.ClientSession(headers=self.headers) as session:
            # Download photos
            for photo in photos:
                result = await self._download_photo(session, photo)
                if result:
                    stats['photos'] += 1
                else:
                    stats['failed'] += 1

            # Download layouts
            for layout in layouts:
                result = await self._download_layout(session, layout)
                if result:
                    stats['layouts'] += 1
                else:
                    stats['failed'] += 1

        return stats

    async def retry_failed_downloads(self, max_retries: int = 3) -> dict:
        """Retry downloads that previously failed."""
        stats = {'photos_retried': 0, 'layouts_retried': 0, 'success': 0}

        # Get failed photos
        failed_photos = self.db_session.query(PropertyPhoto).filter(
            PropertyPhoto.downloaded == False,
            PropertyPhoto.download_error != None
        ).all()

        # Get failed layouts
        failed_layouts = self.db_session.query(PropertyLayout).filter(
            PropertyLayout.downloaded == False,
            PropertyLayout.download_error != None
        ).all()

        self.logger.info(f"Retrying {len(failed_photos)} photos and {len(failed_layouts)} layouts")

        async with aiohttp.ClientSession(headers=self.headers) as session:
            for photo in failed_photos:
                stats['photos_retried'] += 1
                result = await self._download_photo(session, photo)
                if result:
                    stats['success'] += 1

            for layout in failed_layouts:
                stats['layouts_retried'] += 1
                result = await self._download_layout(session, layout)
                if result:
                    stats['success'] += 1

        return stats

    async def run(self, resume: bool = True) -> dict:
        """Main entry point."""
        return await self.download_all_media(resume=resume)
