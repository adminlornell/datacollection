#!/usr/bin/env python3
"""
Command-line interface for the geocoding module.

Usage:
    python -m src.geocoding.cli --address "360 Plantation St"
    python -m src.geocoding.cli --address "360 Plantation St" --provider google
    python -m src.geocoding.cli --compare "360 Plantation St"
    python -m src.geocoding.cli --batch --limit 10
"""

import argparse
import asyncio
import logging
import sys
import time
from typing import Optional

from src.core import settings, get_supabase_client, SupabaseClientError
from src.core.utils.address import is_valid_address
from src.geocoding import (
    geocode_address,
    geocode_batch,
    CensusGeocoder,
    GoogleGeocoder,
    NominatimGeocoder,
)
from src.geocoding.facade import compare_providers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("geocoding.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def test_single_address(
    address: str,
    provider: str = "census",
    verbose: bool = False
) -> None:
    """Test geocoding a single address."""
    print(f"\nGeocoding: {address}")
    print(f"Provider: {provider}")
    print("-" * 50)

    result = await geocode_address(address, provider=provider)

    if result:
        print(f"✓ Success!")
        print(f"  Latitude:  {result.latitude:.6f}")
        print(f"  Longitude: {result.longitude:.6f}")
        print(f"  Matched:   {result.matched_address}")
        print(f"  Confidence: {result.confidence:.2f}")
        print(f"  Match Type: {result.match_type}")
        if verbose and result.raw_response:
            print(f"  Raw Response: {result.raw_response}")
    else:
        print(f"✗ No match found")


async def compare_address(address: str) -> None:
    """Compare geocoding results from multiple providers."""
    print(f"\nComparing providers for: {address}")
    print("=" * 60)

    results = await compare_providers(address)

    for provider, result in results.items():
        print(f"\n{provider.upper()}:")
        if result:
            print(f"  Lat/Lng: {result.latitude:.6f}, {result.longitude:.6f}")
            print(f"  Matched: {result.matched_address}")
            print(f"  Confidence: {result.confidence:.2f}")
        else:
            print(f"  No match")

    # Calculate distances between results
    valid_results = [(k, v) for k, v in results.items() if v is not None]
    if len(valid_results) > 1:
        from src.core.utils.geo import haversine_distance
        print("\nDistance comparison:")
        for i, (p1, r1) in enumerate(valid_results):
            for p2, r2 in valid_results[i+1:]:
                dist = haversine_distance(
                    r1.latitude, r1.longitude,
                    r2.latitude, r2.longitude
                )
                print(f"  {p1} vs {p2}: {dist:.1f}m")


async def batch_geocode_from_db(
    provider: str = "census",
    all_properties: bool = False,
    limit: Optional[int] = None,
    dry_run: bool = False
) -> None:
    """Batch geocode properties from database."""
    try:
        client = get_supabase_client()
    except SupabaseClientError as e:
        print(f"Error: {e}")
        return

    print("Fetching properties from Supabase...")

    # Fetch properties needing geocoding
    all_data = []
    batch_size = 1000
    offset = 0

    while True:
        query = client.table("worcester_data_collection").select("parcel_id, location")

        if not all_properties:
            query = query.or_("ai_latitude.is.null,ai_longitude.is.null")

        query = query.order("parcel_id").range(offset, offset + batch_size - 1)
        result = query.execute()

        if result.data:
            all_data.extend(result.data)
            logger.info(f"Fetched {len(all_data)} properties so far...")

        if not result.data or len(result.data) < batch_size:
            break

        offset += batch_size

        if limit and len(all_data) >= limit:
            all_data = all_data[:limit]
            break

    # Filter valid addresses
    properties = [
        {"id": p["parcel_id"], "address": p["location"]}
        for p in all_data
        if is_valid_address(p.get("location", ""))
    ]

    print(f"Found {len(properties)} valid addresses to geocode")

    if not properties:
        return

    # Geocode
    start_time = time.time()

    from src.geocoding import get_geocoder
    geocoder = get_geocoder(provider)

    results = await geocoder.batch_geocode(properties, concurrency=5)

    elapsed = time.time() - start_time
    successful = sum(1 for r in results.values() if r is not None)

    print(f"\nGeocoded {successful}/{len(properties)} addresses in {elapsed:.1f}s")

    # Update database
    if not dry_run and successful > 0:
        print("Updating database...")
        updated = 0
        for parcel_id, result in results.items():
            if result:
                try:
                    client.table("worcester_data_collection").update({
                        "ai_latitude": result.latitude,
                        "ai_longitude": result.longitude,
                    }).eq("parcel_id", parcel_id).execute()
                    updated += 1
                except Exception as e:
                    logger.error(f"Failed to update {parcel_id}: {e}")

        print(f"Updated {updated} records")
    elif dry_run:
        print("Dry run - no database updates")
        for parcel_id, result in list(results.items())[:10]:
            if result:
                print(f"  {parcel_id}: {result.latitude:.6f}, {result.longitude:.6f}")

    # Summary
    print(f"\n{'='*50}")
    print("GEOCODING SUMMARY")
    print(f"{'='*50}")
    print(f"Total properties:     {len(properties)}")
    print(f"Successfully geocoded: {successful}")
    print(f"Failed/No match:      {len(properties) - successful}")
    print(f"Success rate:         {successful/len(properties)*100:.1f}%")
    print(f"Time elapsed:         {elapsed:.1f}s")


def main():
    parser = argparse.ArgumentParser(
        description="Geocoding CLI for Worcester property data"
    )

    parser.add_argument(
        "--address", "-a",
        type=str,
        help="Geocode a single address"
    )
    parser.add_argument(
        "--provider", "-p",
        type=str,
        default="census",
        choices=["census", "google", "nominatim"],
        help="Geocoding provider to use"
    )
    parser.add_argument(
        "--compare", "-c",
        type=str,
        help="Compare all providers for an address"
    )
    parser.add_argument(
        "--batch", "-b",
        action="store_true",
        help="Batch geocode from database"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Re-geocode all properties (with --batch)"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        help="Limit number of properties to geocode"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't update database"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    if args.compare:
        asyncio.run(compare_address(args.compare))
    elif args.address:
        asyncio.run(test_single_address(args.address, args.provider, args.verbose))
    elif args.batch:
        asyncio.run(batch_geocode_from_db(
            provider=args.provider,
            all_properties=args.all,
            limit=args.limit,
            dry_run=args.dry_run
        ))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
