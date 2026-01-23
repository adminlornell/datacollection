"""
GeoJSON data importer for building permits and business certificates.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Generator

from src.core import get_supabase_client, SupabaseClientError

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


def parse_date(date_str: Optional[str]) -> Optional[str]:
    """
    Parse date string to ISO format.

    Handles formats:
    - MM/DD/YYYY
    - YYYY-MM-DD

    Returns:
        ISO date string or None
    """
    if not date_str or date_str == "N/A":
        return None

    formats = ["%m/%d/%Y", "%Y-%m-%d", "%Y/%m/%d"]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


def normalize_mbl(mbl: Optional[str]) -> Optional[str]:
    """Normalize MBL/parcel ID format."""
    if not mbl:
        return None
    return mbl.strip()


class GeoJSONImporter:
    """
    Import GeoJSON data into Supabase.

    Supports:
    - Building Permits
    - Business Certificates

    Usage:
        importer = GeoJSONImporter()
        stats = importer.import_permits("Building_Permits.geojson")
        print(f"Imported {stats['inserted']} permits")
    """

    def __init__(self, supabase_client=None):
        """
        Initialize importer.

        Args:
            supabase_client: Optional Supabase client (uses default if not provided)
        """
        self.client = supabase_client

    def _get_client(self):
        """Get Supabase client, lazily initialized."""
        if self.client is None:
            self.client = get_supabase_client()
        return self.client

    def _load_geojson(self, file_path: str) -> List[Dict[str, Any]]:
        """Load and parse GeoJSON file."""
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"GeoJSON file not found: {file_path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        features = data.get("features", [])
        logger.info(f"Loaded {len(features)} features from {file_path}")
        return features

    def _batch_insert(
        self,
        table: str,
        records: List[Dict[str, Any]],
        conflict_column: str
    ) -> Dict[str, int]:
        """
        Insert records in batches with conflict handling.

        Returns:
            Dict with 'inserted' and 'skipped' counts
        """
        client = self._get_client()
        inserted = 0
        skipped = 0

        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i:i + BATCH_SIZE]

            try:
                result = client.table(table).upsert(
                    batch,
                    on_conflict=conflict_column
                ).execute()

                inserted += len(batch)

                if (i + BATCH_SIZE) % 1000 == 0 or i + BATCH_SIZE >= len(records):
                    logger.info(f"Progress: {min(i + BATCH_SIZE, len(records))}/{len(records)}")

            except Exception as e:
                logger.error(f"Batch insert error: {e}")
                skipped += len(batch)

        return {"inserted": inserted, "skipped": skipped}

    def import_permits(
        self,
        file_path: str,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Import building permits from GeoJSON.

        Args:
            file_path: Path to Building_Permits.geojson
            dry_run: If True, parse but don't insert

        Returns:
            Dict with import statistics
        """
        features = self._load_geojson(file_path)

        records = []
        for feature in features:
            props = feature.get("properties", {})

            record = {
                "record_number": props.get("Record_Number"),
                "record_type": props.get("Record_Type"),
                "permit_for": props.get("Permit_For"),
                "date_submitted": parse_date(props.get("Date_Submitted")),
                "record_status": props.get("Record_Status"),
                "address": props.get("Address"),
                "mbl": normalize_mbl(props.get("MBL")),
                "occupancy_type": props.get("Occupancy_Type"),
                "permit_issued_date": parse_date(props.get("Permit_Issued_Date")),
                "contractor_name": props.get("Contractor_Name"),
                "object_id": props.get("OBJECTID"),
            }

            # Skip records without required fields
            if record["record_number"]:
                records.append(record)

        logger.info(f"Parsed {len(records)} valid permit records")

        if dry_run:
            return {
                "total": len(features),
                "valid": len(records),
                "inserted": 0,
                "dry_run": True
            }

        # Insert records
        stats = self._batch_insert("building_permits", records, "record_number")

        return {
            "total": len(features),
            "valid": len(records),
            **stats
        }

    def import_certificates(
        self,
        file_path: str,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Import business certificates from GeoJSON.

        Args:
            file_path: Path to Business_Certificates.geojson
            dry_run: If True, parse but don't insert

        Returns:
            Dict with import statistics
        """
        features = self._load_geojson(file_path)
        today = datetime.now().date()

        records = []
        for feature in features:
            props = feature.get("properties", {})

            expiration = parse_date(props.get("EXPIRATION_"))

            record = {
                "certificate_number": props.get("CERTIFICAT"),
                "business_name": props.get("DBA"),
                "address": props.get("ADDRESS"),
                "file_date": parse_date(props.get("FILE_DATE")),
                "expiration_date": expiration,
                "object_id": props.get("OBJECTID"),
                "is_expired": (
                    datetime.strptime(expiration, "%Y-%m-%d").date() < today
                    if expiration else False
                ),
            }

            # Skip records without required fields
            if record["certificate_number"]:
                records.append(record)

        logger.info(f"Parsed {len(records)} valid certificate records")

        if dry_run:
            return {
                "total": len(features),
                "valid": len(records),
                "inserted": 0,
                "dry_run": True
            }

        # Insert records
        stats = self._batch_insert("business_certificates", records, "certificate_number")

        return {
            "total": len(features),
            "valid": len(records),
            **stats
        }

    def import_all(
        self,
        permits_file: Optional[str] = None,
        certs_file: Optional[str] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Import all GeoJSON data files.

        Args:
            permits_file: Path to permits GeoJSON (optional)
            certs_file: Path to certificates GeoJSON (optional)
            dry_run: If True, parse but don't insert

        Returns:
            Dict with combined statistics
        """
        results = {}

        if permits_file:
            logger.info("Importing building permits...")
            results["permits"] = self.import_permits(permits_file, dry_run)

        if certs_file:
            logger.info("Importing business certificates...")
            results["certificates"] = self.import_certificates(certs_file, dry_run)

        return results
