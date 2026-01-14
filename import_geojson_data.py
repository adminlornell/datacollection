#!/usr/bin/env python3
"""
Import Building Permits and Business Certificates GeoJSON data to Supabase.

Usage:
    python import_geojson_data.py                    # Import both datasets
    python import_geojson_data.py --permits-only     # Import only building permits
    python import_geojson_data.py --certs-only       # Import only business certificates
    python import_geojson_data.py --dry-run          # Parse files without importing

Required tables (run in Supabase SQL editor first):

-- Building Permits Table
CREATE TABLE IF NOT EXISTS building_permits (
    id SERIAL PRIMARY KEY,
    record_number TEXT UNIQUE,
    record_type TEXT,
    permit_for TEXT,
    date_submitted DATE,
    record_status TEXT,
    address TEXT,
    mbl TEXT,
    occupancy_type TEXT,
    permit_issued_date DATE,
    contractor_name TEXT,
    object_id INTEGER,
    linked_parcel_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_permits_mbl ON building_permits(mbl);
CREATE INDEX IF NOT EXISTS idx_permits_linked_parcel ON building_permits(linked_parcel_id);
CREATE INDEX IF NOT EXISTS idx_permits_status ON building_permits(record_status);
CREATE INDEX IF NOT EXISTS idx_permits_type ON building_permits(permit_for);
CREATE INDEX IF NOT EXISTS idx_permits_address ON building_permits(address);

-- Business Certificates Table (if not exists)
CREATE TABLE IF NOT EXISTS business_certificates (
    id SERIAL PRIMARY KEY,
    certificate_number TEXT UNIQUE,
    business_name TEXT,
    address TEXT,
    file_date DATE,
    expiration_date DATE,
    object_id INTEGER,
    linked_parcel_id TEXT,
    is_expired BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_certs_address ON business_certificates(address);
CREATE INDEX IF NOT EXISTS idx_certs_business ON business_certificates(business_name);
CREATE INDEX IF NOT EXISTS idx_certs_linked_parcel ON business_certificates(linked_parcel_id);
CREATE INDEX IF NOT EXISTS idx_certs_expired ON business_certificates(is_expired);
"""

import json
import argparse
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

# File paths
PERMITS_FILE = "../Building_Permits.geojson"
CERTS_FILE = "../Business_Certificates_-_1963_to_Present.geojson"

BATCH_SIZE = 500  # Insert in batches


def parse_date(date_str):
    """Parse date string to ISO format or None."""
    if not date_str or date_str == 'N/A':
        return None
    try:
        # Try MM/DD/YYYY format
        dt = datetime.strptime(date_str, '%m/%d/%Y')
        return dt.strftime('%Y-%m-%d')
    except ValueError:
        try:
            # Try other formats
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            return None


def normalize_mbl(mbl):
    """Normalize MBL to match parcel_id format."""
    if not mbl:
        return None
    # Already in correct format like "02-035-00073"
    return mbl.strip()


def is_certificate_expired(exp_date_str):
    """Check if certificate is expired based on expiration date."""
    if not exp_date_str:
        return True
    try:
        exp_date = datetime.strptime(exp_date_str, '%m/%d/%Y')
        return exp_date < datetime.now()
    except ValueError:
        return True


def load_geojson(filepath):
    """Load and parse GeoJSON file."""
    print(f"Loading {filepath}...")
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    features = data.get('features', [])
    print(f"  Found {len(features)} features")
    return features


def transform_permit(feature):
    """Transform a permit feature to database record."""
    props = feature.get('properties', {})
    return {
        'record_number': props.get('Record__'),
        'record_type': props.get('Record_Type'),
        'permit_for': props.get('Permit_For'),
        'date_submitted': parse_date(props.get('Date_Submitted')),
        'record_status': props.get('Record_Status'),
        'address': props.get('Address'),
        'mbl': normalize_mbl(props.get('MBL')),
        'occupancy_type': props.get('Occupancy_Type'),
        'permit_issued_date': parse_date(props.get('Permit_License_Issued_Date')),
        'contractor_name': props.get('Contractor_Name'),
        'object_id': props.get('ObjectId'),
        'linked_parcel_id': normalize_mbl(props.get('MBL'))  # Same as MBL for direct linking
    }


def transform_certificate(feature):
    """Transform a certificate feature to database record."""
    props = feature.get('properties', {})
    exp_date = props.get('Exp_Date')
    return {
        'certificate_number': str(props.get('Cert__')) if props.get('Cert__') else None,
        'business_name': props.get('Business_Name'),
        'address': props.get('Address'),
        'file_date': parse_date(props.get('File_Date')),
        'expiration_date': parse_date(exp_date),
        'object_id': props.get('ObjectId'),
        'linked_parcel_id': None,  # Will be linked via address matching later
        'normalized_address': normalize_address(props.get('Address'))
    }


def normalize_address(address):
    """Normalize address for matching."""
    if not address:
        return None
    # Uppercase, remove extra spaces, standardize abbreviations
    addr = address.upper().strip()
    addr = ' '.join(addr.split())  # Normalize whitespace
    # Remove unit/apt numbers for matching
    import re
    addr = re.sub(r'\s+(APT|UNIT|STE|SUITE|#)\s*\S*', '', addr)
    return addr


def insert_batch(supabase: Client, table: str, records: list, upsert_key: str = None):
    """Insert a batch of records to Supabase."""
    if not records:
        return 0

    try:
        if upsert_key:
            result = supabase.table(table).upsert(
                records,
                on_conflict=upsert_key
            ).execute()
        else:
            result = supabase.table(table).insert(records).execute()
        return len(result.data) if result.data else 0
    except Exception as e:
        print(f"  Error inserting batch: {e}")
        # Try inserting one by one to find problematic records
        success = 0
        for record in records:
            try:
                if upsert_key:
                    supabase.table(table).upsert(
                        record,
                        on_conflict=upsert_key
                    ).execute()
                else:
                    supabase.table(table).insert(record).execute()
                success += 1
            except Exception as e2:
                print(f"    Failed record: {record.get('record_number') or record.get('certificate_number')} - {e2}")
        return success


def import_permits(supabase: Client, dry_run: bool = False):
    """Import building permits from GeoJSON."""
    print("\n" + "=" * 60)
    print("IMPORTING BUILDING PERMITS")
    print("=" * 60)

    features = load_geojson(PERMITS_FILE)

    # Transform all features
    print("Transforming records...")
    records = [transform_permit(f) for f in features]

    # Filter out records without record_number
    valid_records = [r for r in records if r.get('record_number')]
    print(f"  Valid records: {len(valid_records)} / {len(records)}")

    if dry_run:
        print("\n[DRY RUN] Would insert records. Sample:")
        for r in valid_records[:3]:
            print(f"  {r['record_number']}: {r['permit_for']} at {r['address']}")
        return len(valid_records)

    # Insert in batches (plain insert, no upsert)
    print(f"\nInserting {len(valid_records)} permits in batches of {BATCH_SIZE}...")
    total_inserted = 0

    for i in range(0, len(valid_records), BATCH_SIZE):
        batch = valid_records[i:i + BATCH_SIZE]
        inserted = insert_batch(supabase, 'building_permits', batch, upsert_key=None)
        total_inserted += inserted
        print(f"  Batch {i // BATCH_SIZE + 1}: {inserted} inserted (total: {total_inserted})")

    print(f"\nTotal permits imported: {total_inserted}")
    return total_inserted


def import_certificates(supabase: Client, dry_run: bool = False):
    """Import business certificates from GeoJSON."""
    print("\n" + "=" * 60)
    print("IMPORTING BUSINESS CERTIFICATES")
    print("=" * 60)

    # Check current count
    try:
        result = supabase.table('business_certificates').select('id', count='exact').execute()
        print(f"Current records in table: {result.count}")
    except Exception as e:
        print(f"Table check failed (may not exist yet): {e}")

    features = load_geojson(CERTS_FILE)

    # Transform all features
    print("Transforming records...")
    records = [transform_certificate(f) for f in features]

    # Filter out records without certificate_number
    valid_records = [r for r in records if r.get('certificate_number')]
    print(f"  Valid records: {len(valid_records)} / {len(records)}")

    # Count expired vs active based on expiration_date
    from datetime import datetime
    today = datetime.now().date()
    expired = sum(1 for r in valid_records if r.get('expiration_date') and r.get('expiration_date') < str(today))
    active = len(valid_records) - expired
    print(f"  Active certificates: {active}")
    print(f"  Expired certificates: {expired}")

    if dry_run:
        print("\n[DRY RUN] Would insert records. Sample:")
        for r in valid_records[:3]:
            exp = r.get('expiration_date')
            status = "EXPIRED" if (exp and exp < str(today)) else "ACTIVE"
            print(f"  {r['certificate_number']}: {r['business_name']} [{status}]")
        return len(valid_records)

    # Insert in batches (no upsert - use plain insert since we cleared the table)
    print(f"\nInserting {len(valid_records)} certificates in batches of {BATCH_SIZE}...")
    total_inserted = 0

    for i in range(0, len(valid_records), BATCH_SIZE):
        batch = valid_records[i:i + BATCH_SIZE]
        inserted = insert_batch(supabase, 'business_certificates', batch, upsert_key=None)
        total_inserted += inserted
        print(f"  Batch {i // BATCH_SIZE + 1}: {inserted} inserted (total: {total_inserted})")

    print(f"\nTotal certificates imported: {total_inserted}")
    return total_inserted


def link_permits_to_parcels(supabase: Client):
    """Update linked_parcel_id for permits by matching MBL to parcel_id."""
    print("\n" + "=" * 60)
    print("LINKING PERMITS TO PARCELS")
    print("=" * 60)

    # This would require a database function or manual matching
    # For now, the MBL is already stored as linked_parcel_id
    print("Permits are linked via MBL field (same format as parcel_id)")
    print("To verify links, run:")
    print("""
    SELECT COUNT(*) as matched
    FROM building_permits bp
    JOIN worcester_data_collection wdc ON bp.mbl = wdc.parcel_id;
    """)


def main():
    parser = argparse.ArgumentParser(
        description='Import GeoJSON data to Supabase',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--permits-only', action='store_true',
                        help='Import only building permits')
    parser.add_argument('--certs-only', action='store_true',
                        help='Import only business certificates')
    parser.add_argument('--dry-run', action='store_true',
                        help='Parse files without importing')

    args = parser.parse_args()

    # Check config
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: SUPABASE_URL and SUPABASE_KEY must be set in .env")
        sys.exit(1)

    # Initialize Supabase client
    print(f"Connecting to Supabase: {SUPABASE_URL}")
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    results = {}

    if not args.certs_only:
        results['permits'] = import_permits(supabase, args.dry_run)

    if not args.permits_only:
        results['certificates'] = import_certificates(supabase, args.dry_run)

    if not args.dry_run and not args.certs_only:
        link_permits_to_parcels(supabase)

    # Summary
    print("\n" + "=" * 60)
    print("IMPORT SUMMARY")
    print("=" * 60)
    for key, count in results.items():
        print(f"  {key}: {count} records")

    if args.dry_run:
        print("\n[DRY RUN] No data was imported. Run without --dry-run to import.")


if __name__ == '__main__':
    main()
