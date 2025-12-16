# Worcester MA Property Records Scraper

A comprehensive Python scraper for collecting property records from the Worcester, MA GIS website (gis.vgsi.com/worcesterma).

## Features

- **Complete Data Collection**: Scrapes all streets, properties, and detailed property information
- **Media Downloads**: Downloads property photos and layout sketches
- **Resume Capability**: Automatically resumes from where it left off if interrupted
- **Progress Tracking**: Real-time progress monitoring with database persistence
- **Data Export**: Export to CSV and JSON formats
- **Rate Limiting**: Respectful scraping with configurable delays
- **Concurrent Downloads**: Parallel media downloads for efficiency

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                     SCRAPING PIPELINE                          │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Stage 1: STREET SCRAPER                                       │
│  └── Navigates to Streets.aspx                                 │
│  └── Extracts all street names and URLs                        │
│  └── Handles alphabetical pagination                           │
│                                                                │
│  Stage 2: PROPERTY SCRAPER                                     │
│  └── For each street, visits the street page                   │
│  └── Extracts all property listings                            │
│  └── Captures parcel IDs and detail URLs                       │
│                                                                │
│  Stage 3: DETAIL SCRAPER                                       │
│  └── Visits each property's detail page                        │
│  └── Extracts owner info, building details, land info          │
│  └── Captures assessment values and sales history              │
│  └── Identifies photo and layout URLs                          │
│                                                                │
│  Stage 4: MEDIA DOWNLOADER                                     │
│  └── Downloads all property photos                             │
│  └── Downloads all layout sketches                             │
│  └── Organizes by property ID                                  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

## Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd datacollection
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or
   venv\Scripts\activate     # Windows
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install Playwright browsers**
   ```bash
   playwright install chromium
   ```

## Usage

### Run Full Pipeline
```bash
python main.py
```

### Run Individual Stages
```bash
# Scrape only street list
python main.py --streets-only

# Scrape property listings (requires streets)
python main.py --properties-only

# Scrape property details (requires properties)
python main.py --details-only

# Download photos and layouts
python main.py --download-only
```

### Check Progress
```bash
python main.py --status
```

### Export Data
```bash
# Export to both CSV and JSON
python main.py --export

# Export to specific format
python main.py --export --export-format csv
python main.py --export --export-format json
```

### Other Options
```bash
# Start fresh (ignore previous progress)
python main.py --no-resume

# Limit number of items (for testing)
python main.py --details-only --limit 10
```

## Configuration

Environment variables can be set in a `.env` file:

```env
# Database
DATABASE_PATH=worcester_properties.db

# Storage
DATA_DIR=data

# Scraping settings
REQUEST_DELAY=1.0          # Seconds between requests
MAX_RETRIES=3              # Retry attempts for failed requests
TIMEOUT=30000              # Request timeout in milliseconds

# Browser settings
HEADLESS=true              # Run browser in headless mode
SLOW_MO=100                # Delay between browser actions (ms)

# Downloads
MAX_CONCURRENT_DOWNLOADS=5  # Parallel download limit
```

## Data Collected

### Property Information
- **Location**: Address, parcel ID, street
- **Owner**: Name, mailing address
- **Property Details**: Type, land use, zoning, neighborhood
- **Building**: Year built, living area, rooms, bedrooms, bathrooms
- **Structure**: Style, exterior, roof, heating, cooling
- **Land**: Lot size, frontage, depth
- **Assessment**: Land value, building value, total value
- **Sales History**: Past sales with dates and prices
- **Media**: Photos and layout sketches

### Database Schema

```
streets
├── id, name, url, property_count, scraped, scraped_at

properties
├── id, street_id, parcel_id, address
├── owner_name, owner_address
├── property_type, land_use, zoning, neighborhood
├── year_built, living_area, rooms, bedrooms, bathrooms
├── building_style, exterior_wall, roof_type, heating, cooling
├── lot_size, frontage, depth
├── land_value, building_value, total_value
├── extra_features (JSON), building_details (JSON)
├── sales_history (JSON)
└── scraped, photos_downloaded, layout_downloaded

property_photos
├── id, property_id, url, local_path, filename
├── photo_type, description, downloaded

property_layouts
├── id, property_id, url, local_path, filename
├── layout_type, downloaded
```

## Output Structure

```
datacollection/
├── worcester_properties.db    # SQLite database
├── scraper.log                # Log file
└── data/
    ├── photos/
    │   ├── parcel_123/
    │   │   ├── exterior_1_abc123.jpg
    │   │   └── exterior_2_def456.jpg
    │   └── parcel_456/
    │       └── ...
    ├── layouts/
    │   ├── parcel_123/
    │   │   └── sketch_1_ghi789.jpg
    │   └── ...
    └── exports/
        ├── worcester_properties_20240115_120000.csv
        ├── worcester_properties_20240115_120000.json
        └── worcester_sales_history_20240115_120000.csv
```

## Resumability

The scraper automatically tracks progress and can resume from interruptions:

- **Streets**: Tracked in `scraping_progress` table
- **Properties**: Each street marked as `scraped=True` when complete
- **Details**: Each property marked as `scraped=True` when complete
- **Media**: Each photo/layout marked as `downloaded=True` when complete

Simply run the same command again to resume.

## Rate Limiting & Ethics

This scraper is designed to be respectful:

- Default 1-second delay between requests
- Browser-based scraping mimics real user behavior
- No parallel page requests (only media downloads)
- Exponential backoff on failures

Please use responsibly and in accordance with the website's terms of service.

## Troubleshooting

### Browser Issues
```bash
# Reinstall Playwright browsers
playwright install --force chromium
```

### Database Locked
```bash
# Check for other running processes
ps aux | grep python
# Kill any stuck processes
```

### 403 Forbidden Errors
The website may block automated requests. Solutions:
- Ensure `HEADLESS=true` or try `HEADLESS=false`
- Increase `REQUEST_DELAY`
- Check if the website is blocking your IP

### Memory Issues
For large datasets:
- Use `--limit` to process in batches
- Increase system swap space
- Run on a machine with more RAM

## License

This project is for educational purposes. Ensure compliance with applicable laws and website terms of service when using.
