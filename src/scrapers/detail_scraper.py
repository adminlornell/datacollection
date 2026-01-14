"""
Scraper for extracting detailed property information from parcel pages.

This scraper combines:
- Database persistence and resume capability from the pipeline architecture
- Robust extraction logic with direct selectors and multiple fallbacks
- Multi-building support
- Complete field coverage (permits, tax, exemptions, valuation history, etc.)
- Supabase integration for cloud storage
"""
import re
import json
from datetime import datetime
from typing import Dict, Optional, List, Any
from urllib.parse import urljoin

from supabase import create_client, Client

from .base_scraper import BaseScraper
from ..config import BASE_URL, SUPABASE_URL, SUPABASE_KEY
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
    - Valuation history
    - Photos and sketches/layouts
    - Extra features
    - Outbuildings
    - Permits
    - Tax information
    - Exemptions
    """

    def __init__(self, db_session, supabase_client: Client = None):
        """
        Initialize the scraper.
        
        Args:
            db_session: SQLAlchemy database session (for local SQLite)
            supabase_client: Optional Supabase client for cloud storage
        """
        super().__init__(db_session)
        self.supabase = supabase_client
        
        # Initialize Supabase client if not provided but credentials available
        if self.supabase is None and SUPABASE_URL and SUPABASE_KEY:
            self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            self.logger.info("Supabase client initialized")

    # =========================================================================
    # MAIN SCRAPING METHODS
    # =========================================================================

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

        data = {
            'pid': property_obj.parcel_id,
            'url': property_obj.detail_url,
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
        
        # Collect all photos and layouts from buildings
        data['photos'] = []
        data['layouts'] = []
        for bldg in data.get('buildings', []):
            data['photos'].extend(bldg.get('photos', []))
            data['layouts'].extend(bldg.get('layouts', []))
        
        # Add any additional photos found on page
        additional_photos = await self._scrape_additional_photos(
            existing_urls=set(p['url'] for p in data['photos'])
        )
        data['photos'].extend(additional_photos)

        return data

    # =========================================================================
    # BASIC INFO EXTRACTION
    # =========================================================================

    async def _scrape_basic_info(self) -> Dict:
        """Extract basic property information."""
        return {
            'location': await self.safe_get_text("#MainContent_lblLocation"),
            'mblu': await self.safe_get_text("#MainContent_lblMblu"),
            'acct_number': await self.safe_get_text("#MainContent_lblAcctNum"),
            'building_count': await self.safe_get_text("#MainContent_lblBldCount"),
            'parcel_id_display': await self.safe_get_text("#MainContent_lblPid"),
        }

    # =========================================================================
    # OWNER INFO EXTRACTION
    # =========================================================================

    async def _scrape_owner_info(self) -> Dict:
        """Extract owner information."""
        owner_info = {
            'name': await self.safe_get_text("#MainContent_lblOwner") or 
                    await self.safe_get_text("#MainContent_lblGenOwner"),
            'co_owner': await self.safe_get_text("#MainContent_lblCoOwner"),
            'mailing_address': await self.safe_get_text("#MainContent_lblAddr1"),
            'mailing_city_state_zip': await self.safe_get_text("#MainContent_lblAddr2"),
        }
        
        # Try to get full address from multiple lines
        addr_lines = []
        for i in range(1, 5):
            addr = await self.safe_get_text(f"#MainContent_lblAddr{i}")
            if addr:
                addr_lines.append(addr)
        if addr_lines:
            owner_info['full_mailing_address'] = ', '.join(addr_lines)

        return owner_info

    # =========================================================================
    # CURRENT SALE EXTRACTION
    # =========================================================================

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

    # =========================================================================
    # ASSESSMENT EXTRACTION
    # =========================================================================

    async def _scrape_assessment(self) -> Dict:
        """Extract assessment/valuation information."""
        assessment = {
            'total': await self.safe_get_text("#MainContent_lblGenAssessment")
        }

        # Try to get detailed assessment from table
        assessment_rows = await self._get_table_rows("#MainContent_grdCurrentValueAsmt")
        if assessment_rows and isinstance(assessment_rows[0], dict):
            row = assessment_rows[0]
            assessment['valuation_year'] = row.get('Valuation Year')
            assessment['improvements'] = row.get('Improvements')
            assessment['land'] = row.get('Land')
            assessment['total'] = row.get('Total') or assessment['total']

        return assessment

    # =========================================================================
    # BUILDING EXTRACTION (Multi-building support)
    # =========================================================================

    async def _scrape_buildings(self) -> List[Dict]:
        """Extract building information for all buildings on property."""
        buildings = []
        
        for bldg_idx in range(1, 10):  # Support up to 9 buildings
            bldg_prefix = f"#MainContent_ctl0{bldg_idx}"
            year_built = await self.safe_get_text(f"{bldg_prefix}_lblYearBuilt")
            
            if not year_built:
                break  # No more buildings
                
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

            # Building sub-areas with proper value extraction
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
            self.logger.debug(f"Scraped building {bldg_idx}: {building['living_area_sqft']} sqft")

        return buildings

    # =========================================================================
    # LAND INFO EXTRACTION
    # =========================================================================

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
        
        # Extract land fields from tables (fallback for fields in table rows)
        land_table_fields = await self._extract_section_table_fields("Land")
        for key, value in land_table_fields.items():
            if value and not land_info.get(key):
                land_info[key] = value
        
        # Land lines detail table
        land_lines = await self._get_table_rows("#MainContent_grdLand")
        if land_lines:
            land_info['land_lines'] = land_lines

        return land_info

    # =========================================================================
    # HISTORY & TABLES EXTRACTION
    # =========================================================================

    async def _scrape_sales_history(self) -> List[Dict]:
        """Extract sales history."""
        return await self._get_table_rows("#MainContent_grdSales")

    async def _scrape_valuation_history(self) -> List[Dict]:
        """Extract valuation history."""
        return await self._get_table_rows("#MainContent_grdHistoryValuesAsmt")

    async def _scrape_extra_features(self) -> List[Dict]:
        """Extract extra features."""
        features = await self._get_table_rows("#MainContent_grdXf")
        # Filter out "No Data" messages
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

    # =========================================================================
    # TAX INFO EXTRACTION
    # =========================================================================

    async def _scrape_tax_info(self) -> Dict:
        """Extract tax information."""
        return {
            'tax_amount': await self.safe_get_text("#MainContent_lblTaxAmt"),
            'tax_year': await self.safe_get_text("#MainContent_lblTaxYear"),
            'tax_rate': await self.safe_get_text("#MainContent_lblTaxRate"),
        }

    # =========================================================================
    # PHOTO EXTRACTION
    # =========================================================================

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
    # TABLE EXTRACTION UTILITIES
    # =========================================================================

    async def _get_table_rows(self, table_selector: str) -> List[Dict]:
        """
        Extract rows from a table as list of dicts.
        Uses multiple fallback patterns for header and row detection.
        """
        rows = []
        try:
            table = await self.page.query_selector(table_selector)
            if not table:
                return rows

            # Try multiple header patterns
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

            # Try multiple row patterns
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

    async def _extract_section_table_fields(self, section_name: str) -> Dict:
        """Extract all label-value pairs from tables within a named section."""
        data = {}
        try:
            groups = await self.page.query_selector_all("fieldset, [role='group']")
            
            for group in groups:
                group_text = await group.text_content()
                if section_name.lower() not in group_text.lower()[:100]:
                    continue
                    
                tables = await group.query_selector_all("table")
                for table in tables:
                    rows = await table.query_selector_all("tr")
                    for row in rows:
                        cells = await row.query_selector_all("td")
                        if len(cells) >= 2:
                            label = await cells[0].text_content()
                            value = await cells[1].text_content()
                            if label and value:
                                label_clean = re.sub(r'\s*Legend\s*$', '', 
                                                     label.strip().rstrip(':'))
                                key = self._to_snake_case(label_clean)
                                value_clean = re.sub(r'\s*Legend\s*$', '', value.strip())
                                if key and value_clean:
                                    data[key] = value_clean
        except Exception as e:
            self.logger.debug(f"Error extracting section fields: {e}")
        return data

    # =========================================================================
    # PARSING UTILITIES
    # =========================================================================

    def _parse_number(self, value: str) -> Optional[int]:
        """Parse a numeric string, removing commas and non-digits."""
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
    # DATABASE UPDATE
    # =========================================================================

    async def update_property_in_db(self, property_obj: Property, details: Dict):
        """Update property record with scraped details."""
        
        # Basic info
        if details.get('basic_info'):
            info = details['basic_info']
            property_obj.location = info.get('location', property_obj.address)

        # Owner info
        if details.get('owner_info'):
            owner = details['owner_info']
            property_obj.owner_name = owner.get('name', property_obj.owner_name)
            property_obj.owner_address = owner.get('full_mailing_address') or owner.get('mailing_address')

        # Get first building for main property fields
        buildings = details.get('buildings', [])
        if buildings:
            bldg = buildings[0]
            property_obj.year_built = self._parse_int(bldg.get('year_built'))
            property_obj.living_area = self._parse_float(bldg.get('living_area_sqft'))
            
            attrs = bldg.get('attributes', {})
            property_obj.total_rooms = self._parse_int(attrs.get('total_rooms'))
            property_obj.bedrooms = self._parse_int(attrs.get('total_bedrooms'))
            property_obj.bathrooms = self._parse_float(attrs.get('total_full_bthrms'))
            property_obj.stories = self._parse_float(attrs.get('stories'))
            property_obj.building_style = attrs.get('style')
            property_obj.exterior_wall = attrs.get('exterior_wall_1')
            property_obj.roof_type = attrs.get('roof_structure')
            property_obj.heating = attrs.get('heat_type')
            property_obj.cooling = attrs.get('ac_type')
            
            # Store full building details as JSON
            property_obj.building_details = json.dumps(buildings)

        # Land info
        if details.get('land_info'):
            land = details['land_info']
            property_obj.property_type = land.get('description')
            property_obj.land_use = land.get('use_code')
            property_obj.zoning = land.get('zone')
            property_obj.neighborhood = land.get('neighborhood')
            property_obj.lot_size = self._parse_float(land.get('size_sqft'))
            property_obj.frontage = self._parse_float(land.get('frontage'))
            property_obj.depth = self._parse_float(land.get('depth'))
            property_obj.land_details = json.dumps(land)

        # Assessment
        if details.get('assessment'):
            assess = details['assessment']
            property_obj.land_value = self._parse_currency(assess.get('land'))
            property_obj.building_value = self._parse_currency(assess.get('improvements'))
            property_obj.total_value = self._parse_currency(assess.get('total'))

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
        self.logger.info(f"Updated property {property_obj.parcel_id} in database")

    # =========================================================================
    # SUPABASE INTEGRATION
    # =========================================================================

    def save_to_supabase(self, details: Dict) -> bool:
        """
        Save scraped property details to Supabase worcester_data_collection table.
        
        Args:
            details: Dictionary of all scraped property details
            
        Returns:
            True if successful, False otherwise
        """
        if not self.supabase:
            self.logger.warning("Supabase client not configured, skipping cloud save")
            return False
        
        try:
            # Extract primary building attributes for top-level columns
            buildings = details.get('buildings', [])
            first_bldg = buildings[0] if buildings else {}
            attrs = first_bldg.get('attributes', {})
            
            # Extract assessment values
            assessment = details.get('assessment', {})
            
            # Extract land info
            land = details.get('land_info', {})
            
            # Extract current sale
            current_sale = details.get('current_sale', {})
            
            # Extract tax info
            tax = details.get('tax_info', {})
            
            # Extract owner info
            owner = details.get('owner_info', {})
            
            # Parse last sale date
            last_sale_date = None
            if current_sale.get('date'):
                try:
                    # Try common date formats
                    date_str = current_sale['date']
                    for fmt in ['%m/%d/%Y', '%Y-%m-%d', '%m-%d-%Y']:
                        try:
                            last_sale_date = datetime.strptime(date_str, fmt).date().isoformat()
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass
            
            # Build the record for upsert
            record = {
                # Primary Key
                'parcel_id': details.get('pid'),
                
                # Source & Metadata
                'source_url': details.get('url'),
                'scraped_at': details.get('scraped_at'),
                
                # Basic Info
                'location': details.get('basic_info', {}).get('location'),
                'mblu': details.get('basic_info', {}).get('mblu'),
                'acct_number': details.get('basic_info', {}).get('acct_number'),
                'building_count': self._parse_int(details.get('basic_info', {}).get('building_count')),
                
                # Owner Information
                'owner_name': owner.get('name'),
                'co_owner': owner.get('co_owner'),
                'owner_mailing_address': owner.get('full_mailing_address') or owner.get('mailing_address'),
                
                # Assessment Values
                'total_assessed_value': self._parse_currency(assessment.get('total')),
                'land_value': self._parse_currency(assessment.get('land')),
                'improvements_value': self._parse_currency(assessment.get('improvements')),
                
                # Building Basics (from first building)
                'year_built': self._parse_int(first_bldg.get('year_built')),
                'living_area_sqft': self._parse_int(first_bldg.get('living_area_sqft')),
                
                # Land Size
                'lot_size_sqft': self._parse_float(land.get('size_sqft')),
                'lot_size_acres': self._parse_float(land.get('size_acres')),
                
                # Classification
                'zoning': land.get('zone'),
                'use_code': land.get('use_code'),
                'use_description': land.get('description'),
                'neighborhood': land.get('neighborhood'),
                
                # Room Counts
                'bedrooms': self._parse_int(attrs.get('total_bedrooms')),
                'bathrooms': self._parse_float(attrs.get('total_full_bthrms')),
                'total_rooms': self._parse_int(attrs.get('total_rooms')),
                
                # Building Attributes
                'building_style': attrs.get('style'),
                'exterior_wall': attrs.get('exterior_wall_1'),
                'roof_structure': attrs.get('roof_structure'),
                'heat_type': attrs.get('heat_type'),
                'ac_type': attrs.get('ac_type'),
                
                # Most Recent Sale
                'last_sale_price': self._parse_currency(current_sale.get('price')),
                'last_sale_date': last_sale_date,
                'book_page': current_sale.get('book_page'),
                
                # Tax Information
                'tax_amount': self._parse_currency(tax.get('tax_amount')),
                'tax_year': tax.get('tax_year'),
                'tax_rate': self._parse_float(tax.get('tax_rate')),
                
                # JSONB Columns
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
            
            # Remove None values to avoid issues
            record = {k: v for k, v in record.items() if v is not None}
            
            # Upsert to Supabase (insert or update on conflict)
            result = self.supabase.table('worcester_data_collection').upsert(
                record,
                on_conflict='parcel_id'
            ).execute()
            
            self.logger.info(f"Saved property {details.get('pid')} to Supabase")
            return True
            
        except Exception as e:
            self.logger.error(f"Error saving to Supabase: {e}")
            return False

    # =========================================================================
    # MAIN ENTRY POINTS
    # =========================================================================

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
                
                # Also save to Supabase if configured
                if self.supabase:
                    self.save_to_supabase(details)
                
                scraped += 1

            except Exception as e:
                self.logger.error(f"Error scraping {prop.parcel_id}: {e}")
                continue

        self.logger.info(f"Completed. Scraped {scraped} properties")
        return scraped

    async def run(self, resume: bool = True, limit: int = None) -> int:
        """Main entry point."""
        return await self.scrape_all_properties(resume=resume, limit=limit)

    async def scrape_url_to_supabase(self, url: str, parcel_id: str = None) -> Dict:
        """
        Scrape a single property URL and save directly to Supabase.
        
        This method can be used standalone without the local database.
        
        Args:
            url: The VGSI parcel page URL
            parcel_id: Optional parcel ID (extracted from URL if not provided)
            
        Returns:
            Dictionary of scraped property details
        """
        if not parcel_id:
            # Extract parcel_id from URL
            import re
            match = re.search(r'pid=(\d+)', url)
            parcel_id = match.group(1) if match else None
        
        self.logger.info(f"Scraping URL to Supabase: {url}")
        
        await self.navigate(url)
        
        data = {
            'pid': parcel_id,
            'url': url,
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
        self.save_to_supabase(data)
        
        return data

    async def scrape_parcel_ids_to_supabase(self, parcel_ids: List[str]) -> int:
        """
        Scrape multiple properties by parcel ID and save to Supabase.
        
        Args:
            parcel_ids: List of parcel IDs to scrape
            
        Returns:
            Number of properties successfully scraped
        """
        base_url = "https://gis.vgsi.com/worcesterma/Parcel.aspx?pid="
        scraped = 0
        total = len(parcel_ids)
        
        for idx, pid in enumerate(parcel_ids, 1):
            url = f"{base_url}{pid}"
            self.logger.info(f"Progress: {idx}/{total} - Parcel {pid}")
            
            try:
                await self.scrape_url_to_supabase(url, pid)
                scraped += 1
            except Exception as e:
                self.logger.error(f"Error scraping parcel {pid}: {e}")
                continue
        
        self.logger.info(f"Completed. Scraped {scraped}/{total} properties to Supabase")
        return scraped
