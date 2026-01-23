#!/usr/bin/env python3
"""
Fast linking of business certificates to properties using batch SQL.
"""

# Import from core module
from src.core import get_supabase_client
from src.core.utils.address import normalize_address


def main():
    print("Connecting to Supabase...", flush=True)
    supabase = get_supabase_client()

    # Load all properties
    print("\nLoading properties...", flush=True)
    properties = []
    offset = 0
    while True:
        result = supabase.table('worcester_data_collection')\
            .select('parcel_id, location')\
            .range(offset, offset + 999)\
            .execute()
        if not result.data:
            break
        properties.extend(result.data)
        offset += 1000
    print(f"Loaded {len(properties)} properties", flush=True)

    # Build lookup
    lookup = {}
    for p in properties:
        if p.get('location'):
            norm = normalize_address(p['location'])
            if norm:
                lookup[norm] = p['parcel_id']

    # Load unlinked certificates
    print("\nLoading unlinked certificates...", flush=True)
    certs = []
    offset = 0
    while True:
        result = supabase.table('business_certificates')\
            .select('id, address')\
            .is_('linked_parcel_id', 'null')\
            .range(offset, offset + 999)\
            .execute()
        if not result.data:
            break
        certs.extend(result.data)
        offset += 1000
    print(f"Found {len(certs)} unlinked certificates", flush=True)

    # Match
    updates = []
    for cert in certs:
        if cert.get('address'):
            norm = normalize_address(cert['address'])
            parcel_id = lookup.get(norm)
            if parcel_id:
                updates.append({'id': cert['id'], 'linked_parcel_id': parcel_id})

    print(f"\nMatched {len(updates)} certificates", flush=True)

    # Batch update using PostgreSQL function via RPC
    # Fall back to smaller batches with upsert
    if updates:
        print(f"Updating...", flush=True)
        batch_size = 50
        done = 0
        for i in range(0, len(updates), batch_size):
            batch = updates[i:i + batch_size]
            for item in batch:
                try:
                    supabase.table('business_certificates')\
                        .update({'linked_parcel_id': item['linked_parcel_id']})\
                        .eq('id', item['id'])\
                        .execute()
                    done += 1
                except Exception as e:
                    pass  # Skip errors
            if done % 500 == 0 or done == len(updates):
                print(f"  Updated {done}/{len(updates)}", flush=True)

    # Final count
    result = supabase.table('business_certificates')\
        .select('id', count='exact')\
        .not_.is_('linked_parcel_id', 'null')\
        .execute()
    print(f"\n✓ Total linked certificates: {result.count}", flush=True)
    print("\nRefresh the dashboard to see the updated 'Has Business' count!", flush=True)


if __name__ == '__main__':
    main()
