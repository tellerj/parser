"""9-Line format output formatter.

An adapted 9-line report format for air tracks. This is not a formal
military standard — it's a convenience format for quick reference.
"""

from __future__ import annotations

from link16_parser.core.types import Track
from link16_parser.output.coords import position_to_lm


class NineLineFormatter:
    """Formats a ``Track`` as a 9-line convenience report.

    This is *not* a formal military standard — it's an adapted format
    for quick reference. The TACREP format (``TacrepFormatter``) is the
    formal standard and should be the primary output.
    """

    @property
    def name(self) -> str:
        return "9-LINE"

    def format(self, track: Track) -> str:
        """Produce a 9-line air track report.

        Args:
            track: The track to report on.

        Returns:
            A multi-line string with ``LINE 1:`` through ``LINE 9:``.
        """
        tn = track.track_number or str(track.stn)
        aircraft = "UNK"
        if track.platform:
            aircraft = track.platform.specific_type or track.platform.generic_type or "UNK"

        callsign = track.callsign or "UNK"
        position = position_to_lm(track.position) if track.position else "UNK"
        altitude = f"{track.position.alt_m:.0f}M" if track.position and track.position.alt_m is not None else "UNK"
        heading = f"{track.heading_deg:.0f}" if track.heading_deg is not None else "UNK"
        speed = f"{track.speed_kph:.0f}KPH" if track.speed_kph is not None else "UNK"

        dtg = "UNK"
        if track.last_updated:
            ts = track.last_updated
            dtg = f"{ts.day:02d}{ts.hour:02d}{ts.minute:02d}Z"

        identity = track.identity.value if track.identity else "UNK"

        lines = [
            f"LINE 1: {tn}",
            f"LINE 2: {aircraft}",
            f"LINE 3: {callsign}",
            f"LINE 4: {position}",
            f"LINE 5: {altitude}",
            f"LINE 6: {heading}",
            f"LINE 7: {speed}",
            f"LINE 8: {dtg}",
            f"LINE 9: ID:{identity} MSGS:{track.message_count}",
        ]
        return "\n".join(lines)
