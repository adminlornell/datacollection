"""
Consolidated data import module for Worcester property data.

This module provides utilities for:
- Importing GeoJSON data (permits, certificates)
- Linking external data to properties
- Database migrations and setup

Usage:
    from src.data_import import GeoJSONImporter, PropertyLinker

    # Import permits
    importer = GeoJSONImporter()
    importer.import_permits("Building_Permits.geojson")

    # Link certificates to properties
    linker = PropertyLinker()
    linker.link_certificates()
"""

from src.data_import.importers.geojson import GeoJSONImporter
from src.data_import.linkers.property_linker import PropertyLinker

__all__ = [
    "GeoJSONImporter",
    "PropertyLinker",
]
