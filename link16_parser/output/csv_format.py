"""CSV output formatter.

Serializes each Track as a comma-separated row. Nested fields
(position, platform) are flattened into individual columns.
"""

from __future__ import annotations

from link16_parser.core.types import Track
from link16_parser.output.coords import normalize_utc

# Fixed column order — flattened from the Track dataclass.
COLUMNS: list[str] = [
    "stn",
    "status",
    "track_number",
    "callsign",
    "lat",
    "lon",
    "alt_m",
    "identity",
    "generic_type",
    "specific_type",
    "nationality",
    "heading_deg",
    "speed_kph",
    "last_updated",
    "message_count",
]


class CsvFormatter:
    """Formats a ``Track`` as a CSV row.

    Stateless — ``format()`` always returns a data-only row.
    Use ``header()`` to get the column header row. Callers are
    responsible for emitting the header once at the start of a
    stream if needed.

    Nested dataclasses are flattened: ``position.lat`` becomes the
    ``lat`` column, ``platform.specific_type`` becomes ``specific_type``,
    etc. ``None`` values are rendered as empty strings.

    Note: ``track.fields`` is not included in the CSV output. The
    open-schema nature of that dict doesn't fit a fixed-column format.
    Use the JSON formatter if you need ``fields``.
    """

    @property
    def name(self) -> str:
        return "CSV"

    def header(self) -> str:
        """Return the CSV header row."""
        return ",".join(COLUMNS)

    def format(self, track: Track) -> str:
        """Produce a CSV data row for the given track."""
        return ",".join(_track_to_row(track))


def _fmt(value: object) -> str:
    """Format a single value for CSV output.

    None becomes empty string. Strings containing commas or quotes
    are quoted per RFC 4180.
    """
    if value is None:
        return ""
    s = str(value)
    if "," in s or '"' in s or "\n" in s:
        return '"' + s.replace('"', '""') + '"'
    return s


def _track_to_row(track: Track) -> list[str]:
    pos = track.position
    plat = track.platform
    return [
        _fmt(track.stn),
        _fmt(track.status.value),
        _fmt(track.track_number),
        _fmt(track.callsign),
        _fmt(pos.lat if pos else None),
        _fmt(pos.lon if pos else None),
        _fmt(pos.alt_m if pos else None),
        _fmt(track.identity.value if track.identity else None),
        _fmt(plat.generic_type if plat else None),
        _fmt(plat.specific_type if plat else None),
        _fmt(plat.nationality if plat else None),
        _fmt(track.heading_deg),
        _fmt(track.speed_kph),
        _fmt(normalize_utc(track.last_updated).isoformat() if track.last_updated else None),
        _fmt(track.message_count),
    ]
