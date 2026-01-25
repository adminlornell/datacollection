"""
Property linker for connecting external data to Worcester properties.

Links business certificates and building permits to properties by
matching addresses.
"""

import logging
from typing import Dict, Optional, List

from src.core import get_supabase_client
from src.core.utils.address import normalize_address

logger = logging.getLogger(__name__)


class PropertyLinker:
    """
    Link external data sources to Worcester properties.

    Supports:
    - Business certificates -> Properties (by address)
    - Building permits -> Properties (by MBL/parcel_id)

    Usage:
        linker = PropertyLinker()
        stats = linker.link_certificates()
        print(f"Linked {stats['linked']} certificates")
    """

    def __init__(self, supabase_client=None):
        """
        Initialize linker.

        Args:
            supabase_client: Optional Supabase client
        """
        self.client = supabase_client

    def _get_client(self):
        """Get Supabase client, lazily initialized."""
        if self.client is None:
            self.client = get_supabase_client()
        return self.client

    def _build_property_lookup(self) -> Dict[str, str]:
        """
        Build normalized address -> parcel_id lookup from properties.

        Returns:
            Dict mapping normalized addresses to parcel IDs
        """
        client = self._get_client()
        lookup = {}

        logger.info("Building property address lookup...")

        offset = 0
        batch_size = 1000

        while True:
            result = client.table("worcester_data_collection").select(
                "parcel_id, location"
            ).range(offset, offset + batch_size - 1).execute()

            if not result.data:
                break

            for prop in result.data:
                location = prop.get("location")
                if location:
                    normalized = normalize_address(location)
                    if normalized:
                        lookup[normalized] = prop["parcel_id"]

            offset += batch_size

            if len(result.data) < batch_size:
                break

        logger.info(f"Built lookup with {len(lookup)} addresses")
        return lookup

    def link_certificates(
        self,
        dry_run: bool = False,
        batch_size: int = 50
    ) -> Dict[str, int]:
        """
        Link unlinked business certificates to properties by address.

        Args:
            dry_run: If True, don't update database
            batch_size: Number of updates per batch

        Returns:
            Dict with statistics
        """
        client = self._get_client()

        # Build property lookup
        lookup = self._build_property_lookup()

        # Fetch unlinked certificates
        logger.info("Fetching unlinked certificates...")

        certs = []
        offset = 0

        while True:
            result = client.table("business_certificates").select(
                "id, address"
            ).is_("linked_parcel_id", "null").range(
                offset, offset + 999
            ).execute()

            if not result.data:
                break

            certs.extend(result.data)
            offset += 1000

        logger.info(f"Found {len(certs)} unlinked certificates")

        # Match certificates to properties
        matches = []
        for cert in certs:
            address = cert.get("address")
            if address:
                normalized = normalize_address(address)
                parcel_id = lookup.get(normalized)
                if parcel_id:
                    matches.append({
                        "id": cert["id"],
                        "linked_parcel_id": parcel_id
                    })

        logger.info(f"Matched {len(matches)} certificates to properties")

        if dry_run:
            return {
                "total": len(certs),
                "matched": len(matches),
                "updated": 0,
                "dry_run": True
            }

        # Update database
        updated = 0
        for i in range(0, len(matches), batch_size):
            batch = matches[i:i + batch_size]

            for item in batch:
                try:
                    client.table("business_certificates").update({
                        "linked_parcel_id": item["linked_parcel_id"]
                    }).eq("id", item["id"]).execute()
                    updated += 1
                except Exception as e:
                    logger.error(f"Failed to update cert {item['id']}: {e}")

            if updated % 500 == 0 or updated == len(matches):
                logger.info(f"Updated {updated}/{len(matches)} certificates")

        return {
            "total": len(certs),
            "matched": len(matches),
            "updated": updated
        }

    def link_permits(
        self,
        dry_run: bool = False,
        batch_size: int = 50
    ) -> Dict[str, int]:
        """
        Link unlinked building permits to properties by MBL/parcel_id.

        Args:
            dry_run: If True, don't update database
            batch_size: Number of updates per batch

        Returns:
            Dict with statistics
        """
        client = self._get_client()

        # Fetch unlinked permits with MBL
        logger.info("Fetching unlinked permits...")

        permits = []
        offset = 0

        while True:
            result = client.table("building_permits").select(
                "id, mbl"
            ).is_("linked_parcel_id", "null").not_.is_(
                "mbl", "null"
            ).range(offset, offset + 999).execute()

            if not result.data:
                break

            permits.extend(result.data)
            offset += 1000

        logger.info(f"Found {len(permits)} unlinked permits with MBL")

        # Build parcel_id lookup
        parcel_ids = set()
        offset = 0

        while True:
            result = client.table("worcester_data_collection").select(
                "parcel_id"
            ).range(offset, offset + 999).execute()

            if not result.data:
                break

            for prop in result.data:
                parcel_ids.add(prop["parcel_id"])

            offset += 1000

        logger.info(f"Found {len(parcel_ids)} parcel IDs")

        # Match permits to properties (MBL often equals parcel_id)
        matches = []
        for permit in permits:
            mbl = permit.get("mbl")
            if mbl and mbl in parcel_ids:
                matches.append({
                    "id": permit["id"],
                    "linked_parcel_id": mbl
                })

        logger.info(f"Matched {len(matches)} permits to properties")

        if dry_run:
            return {
                "total": len(permits),
                "matched": len(matches),
                "updated": 0,
                "dry_run": True
            }

        # Update database
        updated = 0
        for i in range(0, len(matches), batch_size):
            batch = matches[i:i + batch_size]

            for item in batch:
                try:
                    client.table("building_permits").update({
                        "linked_parcel_id": item["linked_parcel_id"]
                    }).eq("id", item["id"]).execute()
                    updated += 1
                except Exception as e:
                    logger.error(f"Failed to update permit {item['id']}: {e}")

            if updated % 500 == 0 or updated == len(matches):
                logger.info(f"Updated {updated}/{len(matches)} permits")

        return {
            "total": len(permits),
            "matched": len(matches),
            "updated": updated
        }

    def link_all(self, dry_run: bool = False) -> Dict[str, Dict[str, int]]:
        """
        Link all external data to properties.

        Args:
            dry_run: If True, don't update database

        Returns:
            Dict with statistics for each data type
        """
        results = {}

        logger.info("Linking business certificates...")
        results["certificates"] = self.link_certificates(dry_run)

        logger.info("Linking building permits...")
        results["permits"] = self.link_permits(dry_run)

        return results
