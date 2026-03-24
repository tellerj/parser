"""JSON (NDJSON) output formatter.

Serializes each Track as a single-line JSON object — one object per
``format()`` call, suitable for newline-delimited JSON (NDJSON) streams.
No interpretation or opinion applied — just the Track's state as-is.
"""

from __future__ import annotations

import json
from datetime import datetime

from link16_parser.core.types import Track
from link16_parser.output.coords import normalize_utc


class JsonFormatter:
    """Formats a ``Track`` as a single-line JSON object.

    Output is newline-delimited JSON (NDJSON): each ``format()`` call
    returns one self-contained JSON object. Suitable for piping to
    ``jq``, log aggregators, database ingestors, or any tool that
    consumes structured data.

    Nested dataclasses (``Position``, ``PlatformId``) are serialized
    as nested objects. Enums are serialized as their string values.
    ``None`` fields are included explicitly as ``null``.
    """

    @property
    def name(self) -> str:
        return "JSON"

    def format(self, track: Track) -> str:
        """Produce a single-line JSON representation of the track."""
        obj: dict[str, object] = {
            "stn": track.stn,
            "status": track.status.value,
            "track_number": track.track_number,
            "callsign": track.callsign,
            "position": _serialize_position(track),
            "identity": track.identity.value if track.identity else None,
            "platform": _serialize_platform(track),
            "heading_deg": track.heading_deg,
            "speed_kph": track.speed_kph,
            "last_updated": _serialize_dt(track.last_updated),
            "message_count": track.message_count,
        }
        if track.fields:
            obj["fields"] = track.fields

        return json.dumps(obj, separators=(",", ":"))


def _serialize_position(track: Track) -> dict[str, object] | None:
    if track.position is None:
        return None
    return {
        "lat": track.position.lat,
        "lon": track.position.lon,
        "alt_m": track.position.alt_m,
    }


def _serialize_platform(track: Track) -> dict[str, object] | None:
    if track.platform is None:
        return None
    return {
        "generic_type": track.platform.generic_type,
        "specific_type": track.platform.specific_type,
        "nationality": track.platform.nationality,
    }


def _serialize_dt(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return normalize_utc(dt).isoformat()
