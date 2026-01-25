#!/usr/bin/env python3
"""
Update property coordinates in Supabase from Worcester Address_Points.csv.

This script:
1. Reads Address_Points.csv which has Massachusetts State Plane coordinates (EPSG:2249)
2. Converts them to WGS84 lat/lng (EPSG:4326)
3. Updates ai_latitude and ai_longitude in Supabase worcester_data_collection table

Usage:
    python update_coordinates.py                    # Update all properties
    python update_coordinates.py --limit 100        # Update first 100 for testing
    python update_coordinates.py --dry-run          # Show what would be updated
"""
import argparse
import os
import sys
import logging
from datetime import datetime

import pandas as pd
from pyproj import Transformer
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('coordinate_update.log')
    ]
)
logger = logging.getLogger(__name__)

# Path to Address_Points.csv
ADDRESS_POINTS_CSV = "/Users/flyn/dataCollection/worcesterDataCollection/Address_Points.csv"

# Coordinate transformer: MA State Plane (feet) -> WGS84 (lat/lng)
# EPSG:2249 = NAD83 / Massachusetts Mainland (ftUS)
# EPSG:4326 = WGS84 (standard lat/lng)
transformer = Transformer.from_crs("EPSG:2249", "EPSG:4326", always_xy=True)


def convert_state_plane_to_latlon(x: float, y: float) -> tuple:
    """
    Convert Massachusetts State Plane coordinates to WGS84 lat/lng.

    Args:
        x: State Plane X coordinate (feet from origin)
        y: State Plane Y coordinate (feet from origin)

    Returns:
        Tuple of (latitude, longitude)
    """
    lng, lat = transformer.transform(x, y)
    return lat, lng


def load_address_points() -> pd.DataFrame:
    """Load and prepare Address_Points.csv data."""
    logger.info(f"Loading {ADDRESS_POINTS_CSV}...")

    df = pd.read_csv(ADDRESS_POINTS_CSV)
    logger.info(f"Loaded {len(df)} address points")

    # Keep only rows with valid coordinates and parcel IDs
    df = df[df['X'].notna() & df['Y'].notna() & df['MAP_PAR_ID'].notna()]
    logger.info(f"{len(df)} rows have valid coordinates and parcel IDs")

    # Convert coordinates
    logger.info("Converting State Plane coordinates to lat/lng...")
    coords = df.apply(
        lambda row: convert_state_plane_to_latlon(row['X'], row['Y']),
        axis=1
    )
    df['latitude'] = coords.apply(lambda x: x[0])
    df['longitude'] = coords.apply(lambda x: x[1])

    # Group by parcel ID and take the first coordinate for each
    # (some parcels may have multiple address points)
    df_unique = df.groupby('MAP_PAR_ID').first().reset_index()
    logger.info(f"{len(df_unique)} unique parcel IDs with coordinates")

    return df_unique[['MAP_PAR_ID', 'latitude', 'longitude']]


def update_supabase_coordinates(coords_df: pd.DataFrame, limit: int = None, dry_run: bool = False):
    """Update Supabase with coordinates from Address_Points."""

    # Initialize Supabase client
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')

    if not supabase_url or not supabase_key:
        logger.error("SUPABASE_URL and SUPABASE_KEY environment variables are required")
        return

    supabase = create_client(supabase_url, supabase_key)
    logger.info("Connected to Supabase")

    # Get properties from Supabase that need coordinates
    logger.info("Fetching properties from Supabase...")

    # Fetch in batches since there could be many records
    batch_size = 1000
    offset = 0
    all_properties = []

    while True:
        result = supabase.table('worcester_data_collection').select(
            'parcel_id, acct_number, ai_latitude, ai_longitude'
        ).range(offset, offset + batch_size - 1).execute()

        if not result.data:
            break

        all_properties.extend(result.data)
        offset += batch_size

        if len(result.data) < batch_size:
            break

    logger.info(f"Found {len(all_properties)} properties in Supabase")

    # Filter to properties without coordinates
    properties_needing_coords = [
        p for p in all_properties
        if not p.get('ai_latitude') or not p.get('ai_longitude')
    ]
    logger.info(f"{len(properties_needing_coords)} properties need coordinates")

    # Create lookup dictionary from coords_df
    coords_lookup = coords_df.set_index('MAP_PAR_ID')[['latitude', 'longitude']].to_dict('index')

    # Match and update
    matched = 0
    updated = 0
    errors = 0

    properties_to_update = properties_needing_coords if not limit else properties_needing_coords[:limit]

    for i, prop in enumerate(properties_to_update):
        acct_number = prop.get('acct_number')
        parcel_id = prop.get('parcel_id')

        if not acct_number:
            continue

        # Look up coordinates
        if acct_number in coords_lookup:
            coord_data = coords_lookup[acct_number]
            matched += 1

            if dry_run:
                if matched <= 10:  # Show first 10 matches
                    logger.info(f"  Would update {acct_number}: ({coord_data['latitude']:.6f}, {coord_data['longitude']:.6f})")
            else:
                try:
                    supabase.table('worcester_data_collection').update({
                        'ai_latitude': coord_data['latitude'],
                        'ai_longitude': coord_data['longitude']
                    }).eq('parcel_id', parcel_id).execute()
                    updated += 1

                    if updated % 100 == 0:
                        logger.info(f"Updated {updated} properties...")

                except Exception as e:
                    logger.error(f"Error updating {parcel_id}: {e}")
                    errors += 1

        # Progress every 1000
        if (i + 1) % 1000 == 0:
            logger.info(f"Processed {i + 1}/{len(properties_to_update)}...")

    # Summary
    logger.info("=" * 60)
    logger.info("COORDINATE UPDATE COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Properties processed: {len(properties_to_update)}")
    logger.info(f"Matched with Address_Points: {matched}")
    if not dry_run:
        logger.info(f"Successfully updated: {updated}")
        logger.info(f"Errors: {errors}")
    else:
        logger.info("DRY RUN - no updates made")


def update_all_properties(coords_df: pd.DataFrame, limit: int = None, dry_run: bool = False):
    """Update ALL properties in Supabase (not just those missing coordinates)."""

    # Initialize Supabase client
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')

    if not supabase_url or not supabase_key:
        logger.error("SUPABASE_URL and SUPABASE_KEY environment variables are required")
        return

    supabase = create_client(supabase_url, supabase_key)
    logger.info("Connected to Supabase")

    # Create lookup dictionary from coords_df
    coords_lookup = coords_df.set_index('MAP_PAR_ID')[['latitude', 'longitude']].to_dict('index')
    logger.info(f"Coordinate lookup has {len(coords_lookup)} entries")

    # Fetch all properties from Supabase
    logger.info("Fetching all properties from Supabase...")
    batch_size = 1000
    offset = 0
    all_properties = []

    while True:
        result = supabase.table('worcester_data_collection').select(
            'parcel_id, acct_number'
        ).range(offset, offset + batch_size - 1).execute()

        if not result.data:
            break

        all_properties.extend(result.data)
        offset += batch_size

        if len(result.data) < batch_size:
            break

    logger.info(f"Found {len(all_properties)} properties in Supabase")

    if limit:
        all_properties = all_properties[:limit]
        logger.info(f"Limited to {limit} properties")

    # Match and update
    matched = 0
    updated = 0
    errors = 0

    for i, prop in enumerate(all_properties):
        acct_number = prop.get('acct_number')
        parcel_id = prop.get('parcel_id')

        if not acct_number:
            continue

        # Look up coordinates
        if acct_number in coords_lookup:
            coord_data = coords_lookup[acct_number]
            matched += 1

            if dry_run:
                if matched <= 10:
                    logger.info(f"  Would update {acct_number}: ({coord_data['latitude']:.6f}, {coord_data['longitude']:.6f})")
            else:
                try:
                    supabase.table('worcester_data_collection').update({
                        'ai_latitude': coord_data['latitude'],
                        'ai_longitude': coord_data['longitude']
                    }).eq('parcel_id', parcel_id).execute()
                    updated += 1

                    if updated % 500 == 0:
                        logger.info(f"Updated {updated} properties...")

                except Exception as e:
                    logger.error(f"Error updating {parcel_id}: {e}")
                    errors += 1

        if (i + 1) % 5000 == 0:
            logger.info(f"Processed {i + 1}/{len(all_properties)}...")

    # Summary
    logger.info("=" * 60)
    logger.info("COORDINATE UPDATE COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Properties processed: {len(all_properties)}")
    logger.info(f"Matched with Address_Points: {matched}")
    if not dry_run:
        logger.info(f"Successfully updated: {updated}")
        logger.info(f"Errors: {errors}")
    else:
        logger.info("DRY RUN - no updates made")


def main():
    parser = argparse.ArgumentParser(
        description='Update Supabase property coordinates from Worcester Address_Points.csv'
    )
    parser.add_argument('--limit', type=int, help='Limit number of properties to update')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be updated without making changes')
    parser.add_argument('--all', action='store_true', help='Update all properties (not just those missing coordinates)')

    args = parser.parse_args()

    # Load and convert coordinates
    coords_df = load_address_points()

    # Update Supabase
    if args.all:
        update_all_properties(coords_df, limit=args.limit, dry_run=args.dry_run)
    else:
        update_supabase_coordinates(coords_df, limit=args.limit, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
