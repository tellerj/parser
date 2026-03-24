"""Bullseye output formatter.

Expresses each track's position as a bearing and distance from a shared
reference point ("bullseye"). This is a standard tactical format — operators
share a common bullseye and communicate positions as bearing/distance
(e.g., ``BULLSEYE 045/12 FL250``).

Altitudes are rendered as flight levels (hundreds of feet), speeds in
knots, and headings in degrees — all standard aviation units.
"""

from __future__ import annotations

from link16_parser.core.types import Track, TrackStatus
from link16_parser.output.coords import (
    haversine_distance_nm,
    initial_bearing_deg,
    kph_to_knots,
    meters_to_flight_level,
)

class BullseyeFormatter:
    """Formats a ``Track`` as a single-line bullseye report.

    Output example::

        STN:01234 BULLSEYE 045/12 FL250 HDG:090 SPD:450KT ID:FRIEND [VIPER01]

    Args:
        bull_lat: Bullseye latitude in decimal degrees.
        bull_lon: Bullseye longitude in decimal degrees.
    """

    def __init__(
        self,
        bull_lat: float,
        bull_lon: float,
    ) -> None:
        self._bull_lat = bull_lat
        self._bull_lon = bull_lon

    @property
    def name(self) -> str:
        return "BULLSEYE"

    @property
    def reference(self) -> tuple[float, float]:
        """Return the active bullseye reference point as (lat, lon)."""
        return (self._bull_lat, self._bull_lon)

    def format(self, track: Track) -> str:
        """Produce a single-line bullseye report for the given track."""
        parts: list[str] = [f"STN:{track.stn:05d}"]

        # Bearing / distance from bullseye
        if track.position is not None:
            bearing = initial_bearing_deg(
                self._bull_lat, self._bull_lon,
                track.position.lat, track.position.lon,
            )
            distance = haversine_distance_nm(
                self._bull_lat, self._bull_lon,
                track.position.lat, track.position.lon,
            )
            parts.append(f"BULLSEYE {round(bearing):03d}/{round(distance)}")

            # Flight level from altitude
            fl = meters_to_flight_level(track.position.alt_m)
            if fl is not None:
                parts.append(fl)
        else:
            parts.append("BULLSEYE ---/---")

        # Heading
        if track.heading_deg is not None:
            parts.append(f"HDG:{round(track.heading_deg):03d}")

        # Speed in knots
        knots = kph_to_knots(track.speed_kph)
        if knots is not None:
            parts.append(f"SPD:{round(knots)}KT")

        # Identity
        if track.identity is not None:
            parts.append(f"ID:{track.identity.value}")

        # Callsign
        if track.callsign is not None:
            parts.append(f"[{track.callsign}]")

        # Status (only if not ACTIVE)
        if track.status != TrackStatus.ACTIVE:
            parts.append(f"STATUS:{track.status.value}")

        # Extra fields
        for key, val in track.fields.items():
            if isinstance(val, (str, int, float)):
                parts.append(f"{key.upper()}:{val}")

        return " ".join(parts)
