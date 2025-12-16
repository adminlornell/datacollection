"""
Scraper for extracting detailed property information from parcel pages.
"""
import re
import json
from datetime import datetime
from typing import Dict, Optional, List, Any
from urllib.parse import urljoin

from .base_scraper import BaseScraper
from ..config import BASE_URL
from ..models import Property, PropertyPhoto, PropertyLayout


class PropertyDetailScraper(BaseScraper):
    """
    Scrapes detailed property information from individual parcel pages.

    VGSI parcel pages typically contain:
    - Owner information
    - Property characteristics (building details)
    - Land information
    - Assessment values
    - Sales history
    - Photos and sketches/layouts
    """

    async def scrape_property_details(self, property_obj: Property) -> Dict:
        """
        Scrape all details for a property.

        Args:
            property_obj: Property model object with detail_url

        Returns:
            Dictionary of all scraped property details
        """
        self.logger.info(f"Scraping details for: {property_obj.address or property_obj.parcel_id}")

        if not property_obj.detail_url:
            self.logger.warning(f"No detail URL for property: {property_obj.parcel_id}")
            return {}

        await self.navigate(property_obj.detail_url)

        details = {}

        # Scrape different sections
        details['owner_info'] = await self._scrape_owner_info()
        details['property_info'] = await self._scrape_property_info()
        details['building_info'] = await self._scrape_building_info()
        details['land_info'] = await self._scrape_land_info()
        details['assessment'] = await self._scrape_assessment_values()
        details['sales_history'] = await self._scrape_sales_history()
        details['photos'] = await self._scrape_photo_urls()
        details['layouts'] = await self._scrape_layout_urls()
        details['extra_features'] = await self._scrape_extra_features()

        return details

    async def _scrape_owner_info(self) -> Dict:
        """Extract owner information."""
        owner_info = {}

        # Common selectors for owner information
        owner_selectors = {
            'owner_name': [
                "#MainContent_lblOwner",
                "#ctl00_MainContent_lblOwner",
                "[id*='Owner']",
                "td:has-text('Owner') + td",
                ".owner-name",
            ],
            'owner_address': [
                "#MainContent_lblAddress",
                "#ctl00_MainContent_lblCoOwner",
                "[id*='MailingAddress']",
                ".mailing-address",
            ],
        }

        for field, selectors in owner_selectors.items():
            for selector in selectors:
                value = await self.safe_get_text(selector)
                if value:
                    owner_info[field] = value
                    break

        # Try to extract from table format
        if not owner_info:
            owner_info = await self._extract_from_labeled_table('Owner')

        return owner_info

    async def _scrape_property_info(self) -> Dict:
        """Extract general property information."""
        property_info = {}

        # Map of field names to possible selectors/labels
        field_mappings = {
            'location': ['Location', 'Property Location', 'Address'],
            'parcel_id': ['Parcel ID', 'PID', 'Map/Lot', 'Account'],
            'property_type': ['Property Type', 'Use Code', 'Class'],
            'land_use': ['Land Use', 'Use', 'Usage'],
            'zoning': ['Zoning', 'Zone'],
            'neighborhood': ['Neighborhood', 'Nbhd', 'Area'],
            'lot_size': ['Lot Size', 'Acres', 'Land Area', 'Lot Area'],
        }

        for field, labels in field_mappings.items():
            for label in labels:
                value = await self._find_value_by_label(label)
                if value:
                    property_info[field] = value
                    break

        return property_info

    async def _scrape_building_info(self) -> Dict:
        """Extract building/structure information."""
        building_info = {}

        # Building detail field mappings
        field_mappings = {
            'year_built': ['Year Built', 'Yr Built', 'Year Blt'],
            'living_area': ['Living Area', 'Finished Area', 'Gross Area', 'Total Living Area', 'Sq Ft'],
            'total_rooms': ['Total Rooms', 'Rooms', 'Num Rooms'],
            'bedrooms': ['Bedrooms', 'Beds', 'BR'],
            'bathrooms': ['Bathrooms', 'Baths', 'Full Baths', 'Total Baths'],
            'half_baths': ['Half Baths', 'Half Bath'],
            'stories': ['Stories', 'Story', 'Floors', 'Num Stories'],
            'building_style': ['Style', 'Building Style', 'Architectural Style'],
            'exterior_wall': ['Exterior Wall', 'Exterior', 'Siding'],
            'roof_type': ['Roof', 'Roof Type', 'Roofing'],
            'roof_material': ['Roof Material', 'Roof Cover'],
            'foundation': ['Foundation', 'Foundation Type'],
            'basement': ['Basement', 'Basement Type'],
            'heating': ['Heating', 'Heat Type', 'Heat'],
            'cooling': ['Cooling', 'AC', 'Air Conditioning', 'Central Air'],
            'fireplace': ['Fireplace', 'Fireplaces', 'FP'],
            'garage': ['Garage', 'Garage Type', 'Parking'],
            'garage_capacity': ['Garage Capacity', 'Garage Cars', 'Car Capacity'],
            'condition': ['Condition', 'Overall Condition', 'Cond'],
            'grade': ['Grade', 'Quality', 'Construction Grade'],
        }

        for field, labels in field_mappings.items():
            for label in labels:
                value = await self._find_value_by_label(label)
                if value:
                    building_info[field] = value
                    break

        # Also try to navigate to Building tab if available
        building_tab = await self._click_tab('Building')
        if building_tab:
            additional_info = await self._extract_all_labeled_values()
            building_info.update(additional_info)

        return building_info

    async def _scrape_land_info(self) -> Dict:
        """Extract land information."""
        land_info = {}

        field_mappings = {
            'lot_size': ['Lot Size', 'Acres', 'Land Area'],
            'frontage': ['Frontage', 'Front Feet', 'Street Frontage'],
            'depth': ['Depth', 'Lot Depth'],
            'topography': ['Topography', 'Topo'],
            'utilities': ['Utilities', 'Util'],
            'sewer': ['Sewer', 'Sewer Type'],
            'water': ['Water', 'Water Type'],
        }

        for field, labels in field_mappings.items():
            for label in labels:
                value = await self._find_value_by_label(label)
                if value:
                    land_info[field] = value
                    break

        # Try Land tab
        land_tab = await self._click_tab('Land')
        if land_tab:
            additional_info = await self._extract_all_labeled_values()
            land_info.update(additional_info)

        return land_info

    async def _scrape_assessment_values(self) -> Dict:
        """Extract assessment/valuation information."""
        assessment = {}

        field_mappings = {
            'land_value': ['Land Value', 'Land', 'Land Assessment'],
            'building_value': ['Building Value', 'Building', 'Bldg Value', 'Improvements'],
            'total_value': ['Total Value', 'Total', 'Total Assessment', 'Assessed Value'],
            'tax_amount': ['Tax Amount', 'Tax', 'Annual Tax'],
            'assessment_year': ['Assessment Year', 'Year', 'FY'],
        }

        for field, labels in field_mappings.items():
            for label in labels:
                value = await self._find_value_by_label(label)
                if value:
                    # Clean currency values
                    assessment[field] = self._parse_currency(value)
                    break

        return assessment

    async def _scrape_sales_history(self) -> List[Dict]:
        """Extract sales history."""
        sales = []

        # Try to click Sales/Transfer tab
        await self._click_tab('Sales')
        await self._click_tab('Transfer')

        # Look for sales history table
        table_selectors = [
            "#MainContent_grdSales",
            "#ctl00_MainContent_grdSales",
            "table[id*='Sales']",
            "table[id*='Transfer']",
            ".sales-history table",
        ]

        for selector in table_selectors:
            table = await self.page.query_selector(selector)
            if table:
                rows = await table.query_selector_all("tr")
                headers = []

                for i, row in enumerate(rows):
                    cells = await row.query_selector_all("td, th")
                    cell_texts = []
                    for cell in cells:
                        text = await cell.text_content()
                        cell_texts.append(text.strip() if text else "")

                    if i == 0:
                        headers = cell_texts
                    elif cell_texts and any(cell_texts):
                        sale = dict(zip(headers, cell_texts)) if headers else {'data': cell_texts}
                        sales.append(sale)

                if sales:
                    break

        return sales

    async def _scrape_photo_urls(self) -> List[Dict]:
        """Extract photo URLs."""
        photos = []

        # Try to click Photos/Images tab
        await self._click_tab('Photos')
        await self._click_tab('Images')
        await self._click_tab('Photo')

        # Look for images
        img_selectors = [
            "#MainContent_imgPhoto",
            "img[id*='Photo']",
            "img[id*='Image']",
            ".property-photo img",
            ".photo-gallery img",
            "img[src*='Photo']",
            "img[src*='Image']",
            "img[src*='GetImage']",
        ]

        for selector in img_selectors:
            images = await self.get_all_elements(selector)
            for img in images:
                src = await img.get_attribute('src')
                alt = await img.get_attribute('alt') or ""

                if src and not self._is_placeholder_image(src):
                    full_url = urljoin(self.page.url, src)
                    photos.append({
                        'url': full_url,
                        'description': alt,
                        'photo_type': self._determine_photo_type(alt, src)
                    })

        # Also look for photo links
        link_selectors = [
            "a[href*='Photo']",
            "a[href*='Image']",
            "a[href*='GetImage']",
        ]

        for selector in link_selectors:
            links = await self.get_all_elements(selector)
            for link in links:
                href = await link.get_attribute('href')
                if href:
                    full_url = urljoin(self.page.url, href)
                    if full_url not in [p['url'] for p in photos]:
                        photos.append({
                            'url': full_url,
                            'description': '',
                            'photo_type': 'unknown'
                        })

        return photos

    async def _scrape_layout_urls(self) -> List[Dict]:
        """Extract layout/sketch URLs."""
        layouts = []

        # Try to click Sketch/Layout tab
        await self._click_tab('Sketch')
        await self._click_tab('Layout')
        await self._click_tab('Floor Plan')

        # Look for sketch images
        sketch_selectors = [
            "#MainContent_imgSketch",
            "img[id*='Sketch']",
            "img[id*='Layout']",
            "img[src*='Sketch']",
            "img[src*='sketch']",
            ".sketch img",
            ".floor-plan img",
        ]

        for selector in sketch_selectors:
            images = await self.get_all_elements(selector)
            for img in images:
                src = await img.get_attribute('src')
                if src and not self._is_placeholder_image(src):
                    full_url = urljoin(self.page.url, src)
                    layouts.append({
                        'url': full_url,
                        'layout_type': 'sketch'
                    })

        # Also look for sketch links
        link_selectors = [
            "a[href*='Sketch']",
            "a[href*='sketch']",
            "a:text('Sketch')",
            "a:text('Layout')",
        ]

        for selector in link_selectors:
            links = await self.get_all_elements(selector)
            for link in links:
                href = await link.get_attribute('href')
                if href:
                    full_url = urljoin(self.page.url, href)
                    if full_url not in [l['url'] for l in layouts]:
                        layouts.append({
                            'url': full_url,
                            'layout_type': 'sketch'
                        })

        return layouts

    async def _scrape_extra_features(self) -> Dict:
        """Extract additional features and amenities."""
        features = {}

        # Try Features/Extra Features tab
        await self._click_tab('Features')
        await self._click_tab('Extra Features')

        # Extract any feature tables
        feature_table = await self.page.query_selector("table[id*='Feature']")
        if feature_table:
            rows = await feature_table.query_selector_all("tr")
            for row in rows:
                cells = await row.query_selector_all("td")
                if len(cells) >= 2:
                    key = await cells[0].text_content()
                    value = await cells[1].text_content()
                    if key and value:
                        features[key.strip()] = value.strip()

        return features

    async def _find_value_by_label(self, label: str) -> Optional[str]:
        """Find a value by its label text."""
        # Try various patterns to find label-value pairs

        # Pattern 1: Label in <td>, value in next <td>
        try:
            cell = await self.page.query_selector(f"td:has-text('{label}')")
            if cell:
                next_cell = await cell.evaluate_handle("el => el.nextElementSibling")
                if next_cell:
                    text = await next_cell.evaluate("el => el.textContent")
                    if text:
                        return text.strip()
        except Exception:
            pass

        # Pattern 2: Label with id containing the field name
        label_clean = label.replace(' ', '')
        selectors = [
            f"[id*='{label_clean}']",
            f"[id*='lbl{label_clean}']",
            f"span[id*='{label_clean}']",
        ]

        for selector in selectors:
            value = await self.safe_get_text(selector)
            if value and value != label:
                return value

        # Pattern 3: Definition list
        try:
            dt = await self.page.query_selector(f"dt:has-text('{label}')")
            if dt:
                dd = await dt.evaluate_handle("el => el.nextElementSibling")
                if dd:
                    text = await dd.evaluate("el => el.textContent")
                    if text:
                        return text.strip()
        except Exception:
            pass

        return None

    async def _extract_from_labeled_table(self, section_name: str) -> Dict:
        """Extract all label-value pairs from a table section."""
        data = {}

        try:
            # Find section header
            section = await self.page.query_selector(f"*:has-text('{section_name}')")
            if section:
                # Find the nearest table
                table = await section.evaluate_handle("el => el.closest('table') || el.querySelector('table')")
                if table:
                    rows = await table.evaluate("el => Array.from(el.querySelectorAll('tr')).map(r => Array.from(r.querySelectorAll('td')).map(c => c.textContent.trim()))")
                    for row in rows:
                        if len(row) >= 2:
                            data[row[0]] = row[1]
        except Exception:
            pass

        return data

    async def _extract_all_labeled_values(self) -> Dict:
        """Extract all visible label-value pairs from the current page/tab."""
        data = {}

        try:
            # Get all tables with label-value structure
            tables = await self.get_all_elements("table")
            for table in tables:
                rows = await table.query_selector_all("tr")
                for row in rows:
                    cells = await row.query_selector_all("td, th")
                    if len(cells) >= 2:
                        label = await cells[0].text_content()
                        value = await cells[1].text_content()
                        if label and value:
                            data[label.strip()] = value.strip()
        except Exception:
            pass

        return data

    async def _click_tab(self, tab_name: str) -> bool:
        """Try to click a tab/menu item."""
        tab_selectors = [
            f"a:text('{tab_name}')",
            f"[id*='{tab_name}']",
            f".tab:has-text('{tab_name}')",
            f"li:has-text('{tab_name}') a",
            f"button:has-text('{tab_name}')",
        ]

        for selector in tab_selectors:
            try:
                tab = await self.page.query_selector(selector)
                if tab:
                    await tab.click()
                    await self.page.wait_for_load_state('networkidle')
                    await self.delay(0.5)
                    return True
            except Exception:
                continue

        return False

    def _parse_currency(self, value: str) -> Optional[float]:
        """Parse a currency string to float."""
        if not value:
            return None
        try:
            # Remove currency symbols, commas, spaces
            cleaned = re.sub(r'[$,\s]', '', value)
            return float(cleaned)
        except ValueError:
            return value  # Return original if not parseable

    def _is_placeholder_image(self, src: str) -> bool:
        """Check if image URL is a placeholder."""
        placeholder_patterns = ['placeholder', 'no_image', 'blank', 'default']
        src_lower = src.lower()
        return any(p in src_lower for p in placeholder_patterns)

    def _determine_photo_type(self, alt: str, src: str) -> str:
        """Determine the type of photo based on alt text or URL."""
        combined = (alt + src).lower()

        if 'front' in combined or 'exterior' in combined:
            return 'exterior_front'
        elif 'rear' in combined or 'back' in combined:
            return 'exterior_rear'
        elif 'side' in combined:
            return 'exterior_side'
        elif 'aerial' in combined or 'bird' in combined:
            return 'aerial'
        elif 'interior' in combined:
            return 'interior'
        elif 'street' in combined:
            return 'street_view'
        else:
            return 'unknown'

    async def update_property_in_db(self, property_obj: Property, details: Dict):
        """Update property record with scraped details."""
        # Owner info
        if details.get('owner_info'):
            owner = details['owner_info']
            property_obj.owner_name = owner.get('owner_name', property_obj.owner_name)
            property_obj.owner_address = owner.get('owner_address')

        # Property info
        if details.get('property_info'):
            info = details['property_info']
            property_obj.location = info.get('location', property_obj.address)
            property_obj.property_type = info.get('property_type')
            property_obj.land_use = info.get('land_use')
            property_obj.zoning = info.get('zoning')
            property_obj.neighborhood = info.get('neighborhood')
            if info.get('lot_size'):
                try:
                    property_obj.lot_size = float(re.sub(r'[^\d.]', '', str(info['lot_size'])))
                except ValueError:
                    pass

        # Building info
        if details.get('building_info'):
            bldg = details['building_info']
            property_obj.year_built = self._parse_int(bldg.get('year_built'))
            property_obj.living_area = self._parse_float(bldg.get('living_area'))
            property_obj.total_rooms = self._parse_int(bldg.get('total_rooms'))
            property_obj.bedrooms = self._parse_int(bldg.get('bedrooms'))
            property_obj.bathrooms = self._parse_float(bldg.get('bathrooms'))
            property_obj.stories = self._parse_float(bldg.get('stories'))
            property_obj.building_style = bldg.get('building_style')
            property_obj.exterior_wall = bldg.get('exterior_wall')
            property_obj.roof_type = bldg.get('roof_type')
            property_obj.heating = bldg.get('heating')
            property_obj.cooling = bldg.get('cooling')
            property_obj.building_details = json.dumps(bldg)

        # Land info
        if details.get('land_info'):
            land = details['land_info']
            property_obj.frontage = self._parse_float(land.get('frontage'))
            property_obj.depth = self._parse_float(land.get('depth'))
            property_obj.land_details = json.dumps(land)

        # Assessment
        if details.get('assessment'):
            assess = details['assessment']
            property_obj.land_value = self._parse_float(assess.get('land_value'))
            property_obj.building_value = self._parse_float(assess.get('building_value'))
            property_obj.total_value = self._parse_float(assess.get('total_value'))

        # Sales history
        if details.get('sales_history'):
            property_obj.sales_history = json.dumps(details['sales_history'])

        # Extra features
        if details.get('extra_features'):
            property_obj.extra_features = json.dumps(details['extra_features'])

        # Photos
        for photo_data in details.get('photos', []):
            existing = self.db_session.query(PropertyPhoto).filter_by(
                property_id=property_obj.id,
                url=photo_data['url']
            ).first()

            if not existing:
                photo = PropertyPhoto(
                    property_id=property_obj.id,
                    url=photo_data['url'],
                    description=photo_data.get('description'),
                    photo_type=photo_data.get('photo_type'),
                    created_at=datetime.utcnow()
                )
                self.db_session.add(photo)

        # Layouts
        for layout_data in details.get('layouts', []):
            existing = self.db_session.query(PropertyLayout).filter_by(
                property_id=property_obj.id,
                url=layout_data['url']
            ).first()

            if not existing:
                layout = PropertyLayout(
                    property_id=property_obj.id,
                    url=layout_data['url'],
                    layout_type=layout_data.get('layout_type'),
                    created_at=datetime.utcnow()
                )
                self.db_session.add(layout)

        property_obj.scraped = True
        property_obj.scraped_at = datetime.utcnow()

        self.db_session.commit()

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

    async def scrape_all_properties(self, resume: bool = True, limit: int = None) -> int:
        """
        Scrape details for all properties in the database.

        Args:
            resume: If True, skip already scraped properties
            limit: Optional limit on number of properties to scrape

        Returns:
            Number of properties scraped
        """
        query = self.db_session.query(Property)
        if resume:
            query = query.filter_by(scraped=False)
        if limit:
            query = query.limit(limit)

        properties = query.all()
        total = len(properties)

        if total == 0:
            self.logger.info("No properties to scrape")
            return 0

        self.logger.info(f"Scraping details for {total} properties")

        scraped = 0
        for idx, prop in enumerate(properties, 1):
            self.logger.info(f"Progress: {idx}/{total} - {prop.address or prop.parcel_id}")

            try:
                details = await self.scrape_property_details(prop)
                await self.update_property_in_db(prop, details)
                scraped += 1

            except Exception as e:
                self.logger.error(f"Error scraping {prop.parcel_id}: {e}")
                continue

        self.logger.info(f"Completed. Scraped {scraped} properties")
        return scraped

    async def run(self, resume: bool = True, limit: int = None) -> int:
        """Main entry point."""
        return await self.scrape_all_properties(resume=resume, limit=limit)
