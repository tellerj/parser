"""Coordinate and formatting utilities shared by output formatters.

Converts between decimal degrees (from Link 16) and military grid format
(DDMM N/S / DDDMM E/W) used in TACREP reports. Also provides a shared
Day-Time-Group (DTG) formatter.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from link16_parser.core.types import Position


def _split_degrees(decimal_degrees: float) -> tuple[int, int]:
    """Split an absolute decimal-degree value into integer degrees and minutes.

    Handles the edge case where rounding minutes to the nearest integer
    produces 60 — in that case, the degree is incremented and minutes reset
    to 0.
    """
    abs_dd = abs(decimal_degrees)
    degrees = int(abs_dd)
    minutes = round((abs_dd - degrees) * 60)
    if minutes == 60:
        degrees += 1
        minutes = 0
    return degrees, minutes


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
    degrees, minutes = _split_degrees(decimal_degrees)
    return f"{degrees:02d}{minutes:02d}{hemisphere}"


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
    degrees, minutes = _split_degrees(decimal_degrees)
    return f"{degrees:03d}{minutes:02d}{hemisphere}"


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


def normalize_utc(ts: datetime) -> datetime:
    """Ensure a datetime is in UTC.

    If the datetime is timezone-aware but not UTC, it is converted.
    Naive datetimes are returned as-is (assumed to already be UTC).

    Args:
        ts: A datetime, preferably UTC.

    Returns:
        The datetime in UTC.
    """
    if ts.tzinfo is not None and ts.utcoffset() != timezone.utc.utcoffset(None):
        return ts.astimezone(timezone.utc)
    return ts


_EARTH_RADIUS_NM = 3440.065  # Mean Earth radius in nautical miles


def haversine_distance_nm(
    lat1: float, lon1: float, lat2: float, lon2: float,
) -> float:
    """Great-circle distance between two points in nautical miles.

    Uses the haversine formula. Inputs are decimal degrees.

    Args:
        lat1: Latitude of point 1.
        lon1: Longitude of point 1.
        lat2: Latitude of point 2.
        lon2: Longitude of point 2.

    Returns:
        Distance in nautical miles.
    """
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return _EARTH_RADIUS_NM * c


def initial_bearing_deg(
    lat1: float, lon1: float, lat2: float, lon2: float,
) -> float:
    """Initial (forward) bearing from point 1 to point 2.

    Args:
        lat1: Latitude of point 1 (decimal degrees).
        lon1: Longitude of point 1 (decimal degrees).
        lat2: Latitude of point 2 (decimal degrees).
        lon2: Longitude of point 2 (decimal degrees).

    Returns:
        Bearing in degrees, 0–360 (0 = north, 90 = east).
    """
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)

    x = math.sin(dlon) * math.cos(rlat2)
    y = math.cos(rlat1) * math.sin(rlat2) - math.sin(rlat1) * math.cos(rlat2) * math.cos(dlon)
    bearing = math.degrees(math.atan2(x, y))
    return bearing % 360


def meters_to_flight_level(meters: float | None) -> str | None:
    """Convert altitude in meters to a flight level string.

    Args:
        meters: Altitude in meters above sea level, or None.

    Returns:
        Flight level string (e.g. ``"FL250"`` for 25,000 ft), or None.
    """
    if meters is None:
        return None
    feet = meters * 3.28084
    level = round(feet / 100)
    return f"FL{level:03d}"


def kph_to_knots(kph: float | None) -> float | None:
    """Convert speed from kilometers per hour to knots.

    Args:
        kph: Speed in km/h, or None.

    Returns:
        Speed in knots, or None.
    """
    if kph is None:
        return None
    return kph / 1.852


def format_dtg(ts: datetime | None) -> str:
    """Format a timestamp as a Day-Time-Group (``DDHHMMZ``).

    Args:
        ts: A UTC datetime, or ``None`` if unavailable. If the datetime
            is timezone-aware but not UTC, it is converted to UTC first.
            Naive datetimes are assumed to already be UTC.

    Returns:
        A string like ``"311500Z"``, or ``"UNK"`` if *ts* is ``None``.
    """
    if ts is None:
        return "UNK"
    ts = normalize_utc(ts)
    return f"{ts.day:02d}{ts.hour:02d}{ts.minute:02d}Z"
