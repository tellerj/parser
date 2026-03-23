"""Coordinate conversion utilities.

Converts between decimal degrees (from Link 16) and military grid format
(DDMM N/S / DDDMM E/W) used in TACREP reports.
"""

from __future__ import annotations

from link16_parser.core.types import Position


def decimal_to_military_lat(decimal_degrees: float) -> str:
    """Convert latitude in decimal degrees to DDMM + hemisphere format.

    Args:
        decimal_degrees: Latitude in decimal degrees. Positive = North,
            negative = South.

    Returns:
        A string like ``"3615N"`` (2-digit degrees, 2-digit minutes,
        hemisphere letter).

    Examples:
        >>> decimal_to_military_lat(36.25)
        '3615N'
        >>> decimal_to_military_lat(-33.5)
        '3330S'
    """
    hemisphere = "N" if decimal_degrees >= 0 else "S"
    degrees = int(abs(decimal_degrees))
    minutes = (abs(decimal_degrees) - degrees) * 60
    return f"{degrees:02d}{minutes:02.0f}{hemisphere}"


def decimal_to_military_lon(decimal_degrees: float) -> str:
    """Convert longitude in decimal degrees to DDDMM + hemisphere format.

    Args:
        decimal_degrees: Longitude in decimal degrees. Positive = East,
            negative = West.

    Returns:
        A string like ``"11545W"`` (3-digit degrees, 2-digit minutes,
        hemisphere letter).

    Examples:
        >>> decimal_to_military_lon(-115.75)
        '11545W'
        >>> decimal_to_military_lon(5.5)
        '00530E'
    """
    hemisphere = "E" if decimal_degrees >= 0 else "W"
    degrees = int(abs(decimal_degrees))
    minutes = (abs(decimal_degrees) - degrees) * 60
    return f"{degrees:03d}{minutes:02.0f}{hemisphere}"


def position_to_lm(position: Position) -> str:
    """Convert a ``Position`` to a TACREP ``LM:`` field value.

    Args:
        position: A ``Position`` with lat/lon in decimal degrees.

    Returns:
        Concatenated military lat + lon — e.g. ``"3615N11545W"``.
        Suitable for direct insertion into TACREP Line 3.

    Examples:
        >>> position_to_lm(Position(36.25, -115.75))
        '3615N11545W'
    """
    return decimal_to_military_lat(position.lat) + decimal_to_military_lon(position.lon)
