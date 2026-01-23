"""
Text and number formatting utilities.

This module provides consistent formatting functions for display across
the dashboard and other output formats.

Usage:
    from src.core.utils.formatting import format_currency, format_number, escape_html

    format_currency(1500000)  # "$1,500,000"
    format_number(12345)      # "12,345"
    escape_html("<script>")   # "&lt;script&gt;"
"""

import html
from typing import Optional, Union

# Status label mappings
STATUS_LABELS = {
    'new': 'New',
    'contacted': 'Contacted',
    'interested': 'Interested',
    'hot': 'Hot',
    'follow_up': 'Follow-up',
    'not_interested': 'Not Interested',
    'closed': 'Closed',
}

# Priority label mappings
PRIORITY_LABELS = {
    1: 'Low',
    2: 'Medium',
    3: 'High',
    4: 'Very High',
    5: 'Critical',
}


def format_currency(
    value: Optional[Union[int, float, str]],
    include_cents: bool = False,
    default: str = 'N/A'
) -> str:
    """
    Format a number as US currency.

    Args:
        value: Numeric value to format
        include_cents: Include cents in output (default: False)
        default: Default value for None/empty input

    Returns:
        Formatted currency string

    Example:
        >>> format_currency(1500000)
        "$1,500,000"
        >>> format_currency(1500000.50, include_cents=True)
        "$1,500,000.50"
        >>> format_currency(None)
        "N/A"
    """
    if value is None:
        return default

    try:
        num = float(value)
    except (ValueError, TypeError):
        return default

    if include_cents:
        return f"${num:,.2f}"
    else:
        return f"${int(num):,}"


def format_number(
    value: Optional[Union[int, float, str]],
    decimal_places: Optional[int] = None,
    default: str = '0'
) -> str:
    """
    Format a number with thousands separators.

    Args:
        value: Numeric value to format
        decimal_places: Number of decimal places (None for auto)
        default: Default value for None/empty input

    Returns:
        Formatted number string

    Example:
        >>> format_number(12345678)
        "12,345,678"
        >>> format_number(1234.5678, decimal_places=2)
        "1,234.57"
    """
    if value is None:
        return default

    try:
        num = float(value)
    except (ValueError, TypeError):
        return default

    if decimal_places is not None:
        return f"{num:,.{decimal_places}f}"
    elif num == int(num):
        return f"{int(num):,}"
    else:
        return f"{num:,}"


def escape_html(text: Optional[str], default: str = '') -> str:
    """
    Escape HTML special characters to prevent XSS.

    Uses Python's html.escape which handles:
    - & -> &amp;
    - < -> &lt;
    - > -> &gt;
    - " -> &quot;
    - ' -> &#x27;

    Args:
        text: Text to escape
        default: Default value for None/empty input

    Returns:
        HTML-escaped string

    Example:
        >>> escape_html("<script>alert('xss')</script>")
        "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;"
    """
    if not text:
        return default

    return html.escape(str(text), quote=True)


def format_status(status: Optional[str], default: str = 'Unknown') -> str:
    """
    Format a lead status code to human-readable label.

    Args:
        status: Status code (e.g., 'follow_up', 'not_interested')
        default: Default for unknown status codes

    Returns:
        Human-readable status label

    Example:
        >>> format_status('follow_up')
        "Follow-up"
        >>> format_status('not_interested')
        "Not Interested"
    """
    if not status:
        return default

    return STATUS_LABELS.get(status.lower(), status.title())


def format_priority(priority: Optional[int], default: str = 'Unknown') -> str:
    """
    Format a priority number to human-readable label.

    Args:
        priority: Priority number (1-5)
        default: Default for invalid priority

    Returns:
        Human-readable priority label

    Example:
        >>> format_priority(5)
        "Critical"
        >>> format_priority(2)
        "Medium"
    """
    if priority is None:
        return default

    return PRIORITY_LABELS.get(priority, default)


def truncate_text(
    text: Optional[str],
    max_length: int = 100,
    suffix: str = '...'
) -> str:
    """
    Truncate text to a maximum length with suffix.

    Args:
        text: Text to truncate
        max_length: Maximum length including suffix
        suffix: Suffix to append when truncated

    Returns:
        Truncated text

    Example:
        >>> truncate_text("This is a very long text", max_length=15)
        "This is a ve..."
    """
    if not text:
        return ''

    if len(text) <= max_length:
        return text

    return text[:max_length - len(suffix)] + suffix


def format_sqft(value: Optional[Union[int, float]], default: str = 'N/A') -> str:
    """
    Format square footage with units.

    Args:
        value: Square footage value
        default: Default for None/empty

    Returns:
        Formatted string with "sq ft" suffix

    Example:
        >>> format_sqft(2500)
        "2,500 sq ft"
    """
    if value is None:
        return default

    try:
        num = int(float(value))
        return f"{num:,} sq ft"
    except (ValueError, TypeError):
        return default


def format_acres(value: Optional[Union[int, float]], decimal_places: int = 2) -> str:
    """
    Format acreage with units.

    Args:
        value: Acreage value
        decimal_places: Decimal precision

    Returns:
        Formatted string with "acres" suffix

    Example:
        >>> format_acres(1.5)
        "1.50 acres"
    """
    if value is None:
        return 'N/A'

    try:
        num = float(value)
        if num == 1.0:
            return f"{num:.{decimal_places}f} acre"
        return f"{num:.{decimal_places}f} acres"
    except (ValueError, TypeError):
        return 'N/A'


def format_year(value: Optional[Union[int, str]], default: str = 'N/A') -> str:
    """
    Format a year value.

    Args:
        value: Year as int or string
        default: Default for None/invalid

    Returns:
        Year string or default

    Example:
        >>> format_year(1985)
        "1985"
        >>> format_year(0)
        "N/A"
    """
    if value is None:
        return default

    try:
        year = int(value)
        if year <= 0 or year > 2100:
            return default
        return str(year)
    except (ValueError, TypeError):
        return default
