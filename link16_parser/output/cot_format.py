"""Cursor on Target (CoT) XML formatter for TAK integration.

Serializes a ``Track`` as a CoT ``<event>`` XML element suitable for
transmission to ATAK, WinTAK, iTAK, or TAK Server over UDP. Uses only
``xml.etree.ElementTree`` from the standard library — no external
dependencies.

CoT reference:
    https://www.mitre.org/sites/default/files/pdf/09_4937.pdf

Output is a bare XML string (no ``<?xml?>`` prolog) — the standard
framing for CoT events sent as UDP datagrams.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from link16_parser.core.types import Identity, Track
from link16_parser.output.coords import normalize_utc

# Maps Link 16 identity to CoT affiliation character.
# CoT type string format: a-{affil}-{dimension}
#   affil: f=friend, h=hostile, n=neutral, u=unknown, s=suspect
#   dimension: A=air, G=ground, S=surface
_IDENTITY_TO_COT = {
    Identity.FRIEND: "f",
    Identity.ASSUMED_FRIEND: "a",
    Identity.HOSTILE: "h",
    Identity.NEUTRAL: "n",
    Identity.SUSPECT: "s",
    Identity.UNKNOWN: "u",
    Identity.PENDING: "p",
}

# Conversion factor: kph → m/s (CoT <track speed=""> expects m/s)
_KPH_TO_MPS = 1000.0 / 3600.0


def _format_cot_time(dt: datetime) -> str:
    """Format a datetime as CoT-style ISO 8601 with trailing ``Z``."""
    utc = normalize_utc(dt)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class CotFormatter:
    """Formats a ``Track`` as a Cursor on Target XML event.

    Each ``format()`` call returns a self-contained ``<event>`` XML
    string ready to send as a UDP datagram to a TAK endpoint.

    Args:
        stale_seconds: Seconds after ``last_updated`` before the event
            is considered stale by TAK clients. Defaults to 120,
            matching the ``TrackDatabase`` default ``stale_ttl``.
    """

    def __init__(self, stale_seconds: int = 120) -> None:
        self._stale_seconds = stale_seconds

    @property
    def name(self) -> str:
        return "COT"

    def format(self, track: Track) -> str:
        """Produce a CoT XML event string for the given track."""
        # Timestamps
        now = datetime.now(timezone.utc)
        ts = normalize_utc(track.last_updated) if track.last_updated else now
        time_str = _format_cot_time(ts)
        stale_str = _format_cot_time(ts + timedelta(seconds=self._stale_seconds))

        # Skip tracks with no known position — emitting (0, 0) would place
        # a false marker at Null Island on TAK displays.
        pos = track.position
        if pos is None:
            return ""

        # CoT type: a-{affiliation}-A  (Link 16 is predominantly air;
        # ground/surface dimension support can be added when Track carries
        # a battle-dimension field.)
        affil = _IDENTITY_TO_COT.get(track.identity, "u") if track.identity else "u"
        cot_type = f"a-{affil}-A"

        # <event>
        event = ET.Element(
            "event",
            version="2.0",
            uid=f"link16-{track.stn}",
            type=cot_type,
            how="m-f",
            time=time_str,
            start=time_str,
            stale=stale_str,
        )

        # <point>
        ET.SubElement(
            event,
            "point",
            lat=str(pos.lat),
            lon=str(pos.lon),
            hae=str(pos.alt_m) if pos.alt_m is not None else "9999999",
            ce="9999999",
            le="9999999",
        )

        # <detail>
        detail = ET.SubElement(event, "detail")

        if track.callsign:
            ET.SubElement(detail, "contact", callsign=track.callsign)

        if track.heading_deg is not None or track.speed_kph is not None:
            attrs: dict[str, str] = {}
            if track.heading_deg is not None:
                attrs["course"] = str(track.heading_deg)
            if track.speed_kph is not None:
                attrs["speed"] = str(track.speed_kph * _KPH_TO_MPS)
            ET.SubElement(detail, "track", attrib=attrs)

        ET.SubElement(
            detail,
            "precisionlocation",
            geopointsrc="CALCULATED",
            altsrc="CALCULATED",
        )

        # <remarks> with STN and optional track number
        parts = [f"STN {track.stn}"]
        if track.track_number:
            parts.append(f"TN {track.track_number}")
        remarks = ET.SubElement(detail, "remarks")
        remarks.text = " | ".join(parts)

        return ET.tostring(event, encoding="unicode")
