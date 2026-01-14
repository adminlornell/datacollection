#!/usr/bin/env python3
"""
Link business certificates and building permits to properties.
"""

import os
import re
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')


def normalize_address(addr):
    """Normalize address for matching."""
    if not addr:
        return None
    # Uppercase, strip, normalize whitespace
    addr = addr.upper().strip()
    addr = ' '.join(addr.split())
    # Remove unit/apt/suite for matching
    addr = re.sub(r'\s+(APT|UNIT|STE|SUITE|FL|FLOOR|#)\s*\S*', '', addr)
    # Standardize common abbreviations
    addr = addr.replace(' STREET', ' ST')
    addr = addr.replace(' AVENUE', ' AVE')
    addr = addr.replace(' ROAD', ' RD')
    addr = addr.replace(' DRIVE', ' DR')
    addr = addr.replace(' LANE', ' LN')
    addr = addr.replace(' COURT', ' CT')
    addr = addr.replace(' PLACE', ' PL')
    addr = addr.replace(' BOULEVARD', ' BLVD')
    return addr


def extract_street_number(addr):
    """Extract street number from address."""
    if not addr:
        return None
    match = re.match(r'^(\d+)', addr)
    return match.group(1) if match else None


def extract_street_name(addr):
    """Extract first word of street name."""
    if not addr:
        return None
    # Remove street number
    addr = re.sub(r'^\d+\s+', '', addr)
    # Get first word
    parts = addr.split()
    return parts[0] if parts else None


def main():
    print("Connecting to Supabase...")
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Load all property locations
    print("\nLoading property locations...")
    properties = []
    offset = 0
    batch_size = 1000
    while True:
        result = supabase.table('worcester_data_collection')\
            .select('parcel_id, location')\
            .range(offset, offset + batch_size - 1)\
            .execute()
        if not result.data:
            break
        properties.extend(result.data)
        offset += batch_size
        print(f"  Loaded {len(properties)} properties...")

    print(f"Total properties loaded: {len(properties)}")

    # Build lookup indexes
    print("\nBuilding address lookup indexes...")
    exact_lookup = {}  # normalized address -> parcel_id
    fuzzy_lookup = {}  # (street_num, first_word) -> parcel_id

    for prop in properties:
        parcel_id = prop.get('parcel_id')
        location = prop.get('location')
        if not parcel_id or not location:
            continue

        norm = normalize_address(location)
        if norm:
            exact_lookup[norm] = parcel_id

        street_num = extract_street_number(location.upper().strip())
        street_name = extract_street_name(normalize_address(location))
        if street_num and street_name:
            key = (street_num, street_name)
            if key not in fuzzy_lookup:
                fuzzy_lookup[key] = parcel_id

    print(f"  Exact lookup entries: {len(exact_lookup)}")
    print(f"  Fuzzy lookup entries: {len(fuzzy_lookup)}")

    # Link business certificates
    print("\n" + "=" * 60)
    print("LINKING BUSINESS CERTIFICATES")
    print("=" * 60)

    # Load certificates
    print("Loading certificates without linked_parcel_id...")
    certs = []
    offset = 0
    while True:
        result = supabase.table('business_certificates')\
            .select('id, address')\
            .is_('linked_parcel_id', 'null')\
            .range(offset, offset + batch_size - 1)\
            .execute()
        if not result.data:
            break
        certs.extend(result.data)
        offset += batch_size

    print(f"Certificates to link: {len(certs)}")

    # Match and update
    matched = 0
    unmatched = 0
    updates = []

    for cert in certs:
        cert_id = cert['id']
        address = cert.get('address')

        if not address:
            unmatched += 1
            continue

        # Try exact match
        norm = normalize_address(address)
        parcel_id = exact_lookup.get(norm)

        # Try fuzzy match
        if not parcel_id:
            street_num = extract_street_number(address.upper().strip())
            street_name = extract_street_name(normalize_address(address))
            if street_num and street_name:
                parcel_id = fuzzy_lookup.get((street_num, street_name))

        if parcel_id:
            updates.append({'id': cert_id, 'linked_parcel_id': parcel_id})
            matched += 1
        else:
            unmatched += 1

    print(f"Matched: {matched}, Unmatched: {unmatched}")

    # Batch update
    if updates:
        print(f"\nUpdating {len(updates)} certificates...")
        batch_size = 100
        for i in range(0, len(updates), batch_size):
            batch = updates[i:i + batch_size]
            for item in batch:
                try:
                    supabase.table('business_certificates')\
                        .update({'linked_parcel_id': item['linked_parcel_id']})\
                        .eq('id', item['id'])\
                        .execute()
                except Exception as e:
                    print(f"  Error updating cert {item['id']}: {e}")
            print(f"  Updated {min(i + batch_size, len(updates))} / {len(updates)}")
        print(f"Done! Linked {matched} business certificates to properties.")

    # Verify
    result = supabase.table('business_certificates')\
        .select('id', count='exact')\
        .not_.is_('linked_parcel_id', 'null')\
        .execute()
    print(f"\nTotal certificates with linked_parcel_id: {result.count}")

    print("\n" + "=" * 60)
    print("COMPLETE - Refresh dashboard to see updated counts")
    print("=" * 60)


if __name__ == '__main__':
    main()
