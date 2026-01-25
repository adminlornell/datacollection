#!/usr/bin/env python3
"""
Command-line interface for data import operations.

Usage:
    python -m src.data_import.cli import --permits Building_Permits.geojson
    python -m src.data_import.cli import --certs Business_Certificates.geojson
    python -m src.data_import.cli link --certificates
    python -m src.data_import.cli link --permits
    python -m src.data_import.cli link --all
"""

import argparse
import logging
import sys

from src.data_import.importers.geojson import GeoJSONImporter
from src.data_import.linkers.property_linker import PropertyLinker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def cmd_import(args):
    """Handle import command."""
    importer = GeoJSONImporter()

    if args.permits:
        logger.info(f"Importing permits from {args.permits}")
        stats = importer.import_permits(args.permits, dry_run=args.dry_run)
        print(f"\nPermits Import Results:")
        print(f"  Total features: {stats['total']}")
        print(f"  Valid records:  {stats['valid']}")
        print(f"  Inserted:       {stats['inserted']}")
        if args.dry_run:
            print("  (DRY RUN - no data imported)")

    if args.certs:
        logger.info(f"Importing certificates from {args.certs}")
        stats = importer.import_certificates(args.certs, dry_run=args.dry_run)
        print(f"\nCertificates Import Results:")
        print(f"  Total features: {stats['total']}")
        print(f"  Valid records:  {stats['valid']}")
        print(f"  Inserted:       {stats['inserted']}")
        if args.dry_run:
            print("  (DRY RUN - no data imported)")


def cmd_link(args):
    """Handle link command."""
    linker = PropertyLinker()

    if args.all or args.certificates:
        logger.info("Linking business certificates...")
        stats = linker.link_certificates(dry_run=args.dry_run)
        print(f"\nCertificate Linking Results:")
        print(f"  Total unlinked: {stats['total']}")
        print(f"  Matched:        {stats['matched']}")
        print(f"  Updated:        {stats['updated']}")
        if args.dry_run:
            print("  (DRY RUN - no data updated)")

    if args.all or args.permits:
        logger.info("Linking building permits...")
        stats = linker.link_permits(dry_run=args.dry_run)
        print(f"\nPermit Linking Results:")
        print(f"  Total unlinked: {stats['total']}")
        print(f"  Matched:        {stats['matched']}")
        print(f"  Updated:        {stats['updated']}")
        if args.dry_run:
            print("  (DRY RUN - no data updated)")


def main():
    parser = argparse.ArgumentParser(
        description="Worcester property data import and linking CLI"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Import command
    import_parser = subparsers.add_parser("import", help="Import data files")
    import_parser.add_argument(
        "--permits",
        type=str,
        help="Path to Building_Permits.geojson"
    )
    import_parser.add_argument(
        "--certs",
        type=str,
        help="Path to Business_Certificates.geojson"
    )
    import_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse files without importing"
    )

    # Link command
    link_parser = subparsers.add_parser("link", help="Link data to properties")
    link_parser.add_argument(
        "--certificates",
        action="store_true",
        help="Link business certificates"
    )
    link_parser.add_argument(
        "--permits",
        action="store_true",
        help="Link building permits"
    )
    link_parser.add_argument(
        "--all",
        action="store_true",
        help="Link all data types"
    )
    link_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be linked without updating"
    )

    args = parser.parse_args()

    if args.command == "import":
        if not args.permits and not args.certs:
            import_parser.error("Must specify --permits or --certs")
        cmd_import(args)
    elif args.command == "link":
        if not args.all and not args.certificates and not args.permits:
            link_parser.error("Must specify --all, --certificates, or --permits")
        cmd_link(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
