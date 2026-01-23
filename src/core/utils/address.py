"""
Address normalization and parsing utilities.

This module consolidates address handling functions used across the codebase
for consistent address matching and comparison.

Usage:
    from src.core.utils.address import normalize_address, is_valid_address

    # Normalize for comparison
    addr1 = normalize_address("123 MAIN STREET, Worcester, MA 01610")
    addr2 = normalize_address("123 Main St")
    assert addr1 == addr2  # "123 MAIN ST"

    # Validate address
    is_valid_address("123 Main St")  # True
    is_valid_address("0 PARCEL")  # False
"""

import re
from typing import Optional, Tuple

# Street type abbreviations (comprehensive list)
STREET_ABBREVIATIONS = {
    # Standard abbreviations
    r'\bSTREET\b': 'ST',
    r'\bAVENUE\b': 'AVE',
    r'\bDRIVE\b': 'DR',
    r'\bROAD\b': 'RD',
    r'\bBOULEVARD\b': 'BLVD',
    r'\bLANE\b': 'LN',
    r'\bCOURT\b': 'CT',
    r'\bCIRCLE\b': 'CIR',
    r'\bPLACE\b': 'PL',
    r'\bTERRACE\b': 'TER',
    r'\bWAY\b': 'WAY',
    r'\bPARKWAY\b': 'PKWY',
    r'\bHIGHWAY\b': 'HWY',
    r'\bEXPRESSWAY\b': 'EXPY',
    r'\bSQUARE\b': 'SQ',
    r'\bTRAIL\b': 'TRL',
    r'\bALLEY\b': 'ALY',
    r'\bPATH\b': 'PATH',
    r'\bGREEN\b': 'GRN',
    r'\bCOMMON\b': 'CMN',
}

# Directional abbreviations
DIRECTIONAL_ABBREVIATIONS = {
    r'\bNORTH\b': 'N',
    r'\bSOUTH\b': 'S',
    r'\bEAST\b': 'E',
    r'\bWEST\b': 'W',
    r'\bNORTHEAST\b': 'NE',
    r'\bNORTHWEST\b': 'NW',
    r'\bSOUTHEAST\b': 'SE',
    r'\bSOUTHWEST\b': 'SW',
}

# Unit type patterns to remove
UNIT_PATTERN = re.compile(
    r'\s+(APT|UNIT|STE|SUITE|FL|FLOOR|#|BLDG|BUILDING|RM|ROOM)\s*\S*',
    re.IGNORECASE
)

# City/State/ZIP pattern (Worcester specific)
CITY_STATE_PATTERN = re.compile(
    r',?\s*(WORCESTER|SHREWSBURY|AUBURN|MILLBURY|LEICESTER|HOLDEN|WEST BOYLSTON|PAXTON|GRAFTON)\s*,?\s*(MA|MASSACHUSETTS)?\s*\d{5}(-\d{4})?$',
    re.IGNORECASE
)

# Invalid address prefixes
INVALID_PREFIXES = ['0 ', '00 ', 'PARCEL', 'LAND', 'REAR', 'OFF ']


def normalize_address(
    address: str,
    remove_city_state: bool = True,
    remove_unit: bool = True,
    abbreviate_streets: bool = True
) -> str:
    """
    Normalize an address for consistent comparison and matching.

    Performs the following transformations:
    1. Convert to uppercase
    2. Remove extra whitespace
    3. Optionally remove unit/apt numbers
    4. Optionally remove city, state, ZIP
    5. Optionally abbreviate street types
    6. Normalize directional prefixes

    Args:
        address: Raw address string
        remove_city_state: Remove city, state, ZIP suffix (default: True)
        remove_unit: Remove unit/apt/suite numbers (default: True)
        abbreviate_streets: Convert street types to abbreviations (default: True)

    Returns:
        Normalized address string, or empty string if input is None/empty

    Example:
        >>> normalize_address("123 Main Street, Apt 4B, Worcester, MA 01610")
        "123 MAIN ST"
        >>> normalize_address("456 NORTH AVENUE")
        "456 N AVE"
    """
    if not address:
        return ""

    # Convert to uppercase and strip
    addr = address.upper().strip()

    # Normalize whitespace
    addr = ' '.join(addr.split())

    # Remove city, state, ZIP
    if remove_city_state:
        addr = CITY_STATE_PATTERN.sub('', addr)
        # Also handle simple ", WORCESTER" without state
        addr = re.sub(r',?\s*WORCESTER.*$', '', addr)

    # Remove unit/apt numbers
    if remove_unit:
        addr = UNIT_PATTERN.sub('', addr)

    # Abbreviate street types
    if abbreviate_streets:
        for pattern, replacement in STREET_ABBREVIATIONS.items():
            addr = re.sub(pattern, replacement, addr)

        # Abbreviate directionals
        for pattern, replacement in DIRECTIONAL_ABBREVIATIONS.items():
            addr = re.sub(pattern, replacement, addr)

    # Final cleanup
    addr = re.sub(r'\s+', ' ', addr).strip()

    # Remove trailing punctuation
    addr = addr.rstrip('.,;')

    return addr


def parse_street_number(address: str) -> Tuple[Optional[int], Optional[str]]:
    """
    Parse the street number from an address.

    Args:
        address: Address string

    Returns:
        Tuple of (street_number, rest_of_address)
        street_number is None if not found

    Example:
        >>> parse_street_number("123 Main St")
        (123, "Main St")
        >>> parse_street_number("Main St")
        (None, "Main St")
    """
    if not address:
        return None, None

    # Match leading number (optionally with letter suffix like "123A")
    match = re.match(r'^(\d+[A-Z]?)\s+(.+)$', address.strip(), re.IGNORECASE)

    if match:
        num_str = match.group(1)
        rest = match.group(2)

        # Extract numeric part
        num_match = re.match(r'^(\d+)', num_str)
        if num_match:
            return int(num_match.group(1)), rest

    return None, address


def is_valid_address(address: str) -> bool:
    """
    Check if an address appears to be valid for geocoding.

    Rejects addresses that:
    - Are empty or None
    - Start with "0 " or "00 "
    - Start with "PARCEL", "LAND", "REAR", etc.
    - Have no street number
    - Are too short (< 5 characters)

    Args:
        address: Address to validate

    Returns:
        True if address appears valid

    Example:
        >>> is_valid_address("123 Main St")
        True
        >>> is_valid_address("0 PARCEL 123")
        False
        >>> is_valid_address("")
        False
    """
    if not address:
        return False

    addr = address.upper().strip()

    # Too short
    if len(addr) < 5:
        return False

    # Check invalid prefixes
    for prefix in INVALID_PREFIXES:
        if addr.startswith(prefix):
            return False

    # Must have a street number
    street_num, _ = parse_street_number(addr)
    if street_num is None or street_num == 0:
        return False

    return True


def extract_street_name(address: str) -> Optional[str]:
    """
    Extract the street name from an address.

    Args:
        address: Full address string

    Returns:
        Street name without number, or None if not found

    Example:
        >>> extract_street_name("123 Main Street, Worcester, MA")
        "MAIN ST"
    """
    if not address:
        return None

    # Normalize first
    normalized = normalize_address(address)

    # Remove street number
    _, street_name = parse_street_number(normalized)

    return street_name


def addresses_match(addr1: str, addr2: str, fuzzy: bool = False) -> bool:
    """
    Check if two addresses refer to the same location.

    Args:
        addr1: First address
        addr2: Second address
        fuzzy: If True, allow partial matches (street name only)

    Returns:
        True if addresses match

    Example:
        >>> addresses_match("123 Main St", "123 MAIN STREET, WORCESTER MA")
        True
    """
    norm1 = normalize_address(addr1)
    norm2 = normalize_address(addr2)

    if not norm1 or not norm2:
        return False

    # Exact match after normalization
    if norm1 == norm2:
        return True

    # Fuzzy matching
    if fuzzy:
        num1, street1 = parse_street_number(norm1)
        num2, street2 = parse_street_number(norm2)

        # Same street number and street name matches
        if num1 == num2 and street1 and street2:
            # Check if one street name contains the other
            return street1 in street2 or street2 in street1

    return False
