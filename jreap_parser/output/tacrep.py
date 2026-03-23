"""TACREP (Tactical Report) output formatter.

Produces AIROP-format TACREPs per the standard TACREP message format.
Output is copy/paste ready for direct dissemination.
"""

from __future__ import annotations

from jreap_parser.core.types import Track
from jreap_parser.output.coords import position_to_lm


class TacrepFormatter:
    """Formats a ``Track`` as a 5-line AIROP TACREP.

    Output matches the format in ``TACREP_FORMAT.md`` and Example #3
    from the reference images (AIROP with F-16Cs). Fields that haven't
    been decoded yet are rendered as ``"UNK"``.

    Args:
        originator: The ``MSGID`` originator field — e.g. ``"CTF124"``,
            ``"1 BDE"``. Appears on Line 2.
        classification: Classification marking on Line 1. Defaults to
            ``"UNCLAS"``. Set to ``"SECRET"`` etc. as appropriate.
    """

    def __init__(
        self,
        originator: str = "JREAP-PARSER",
        classification: str = "UNCLAS",
    ) -> None:
        self._originator = originator
        self._classification = classification

    @property
    def name(self) -> str:
        return "TACREP"

    def format(self, track: Track) -> str:
        """Produce a 5-line AIROP TACREP for the given track.

        Args:
            track: The track to report on.

        Returns:
            A multi-line string (newline-separated, no trailing newline)::

                UNCLAS
                MSGID/TACREP/JREAP-PARSER//
                AIROP/311500Z/1/US/FTR/F16C/TN:225/LM:3015N08000W//
                CRS:200/SPD:650KPH/ALT:2500M//
                AMPN/RULDOG01//
        """
        # Line 1: Classification
        line1 = self._classification

        # Line 2: MSGID
        line2 = f"MSGID/TACREP/{self._originator}//"

        # Line 3: AIROP
        dtg = self._format_dtg(track)
        amount = "1"  # Per-track, so always 1
        nationality = track.platform.nationality if track.platform and track.platform.nationality else "UNK"
        subject_type = track.platform.generic_type if track.platform and track.platform.generic_type else "UNK"
        aircraft_type = track.platform.specific_type if track.platform and track.platform.specific_type else "UNK"
        tn = track.track_number or str(track.stn)
        location = f"LM:{position_to_lm(track.position)}" if track.position else "LM:UNK"

        line3 = f"AIROP/{dtg}/{amount}/{nationality}/{subject_type}/{aircraft_type}/TN:{tn}/{location}//"

        # Line 4: Amplifying data (course/speed/altitude if available)
        amp_parts = []
        if track.heading_deg is not None:
            amp_parts.append(f"CRS:{track.heading_deg:.0f}")
        if track.speed_kph is not None:
            amp_parts.append(f"SPD:{track.speed_kph:.0f}KPH")
        if track.position and track.position.alt_m is not None:
            amp_parts.append(f"ALT:{track.position.alt_m:.0f}M")

        if amp_parts:
            line4 = "/".join(amp_parts) + "//"
        else:
            line4 = "AMPN/NO AMPLIFYING DATA//"

        # Line 5: Callsign / comms
        if track.callsign:
            line5 = f"AMPN/{track.callsign}//"
        else:
            line5 = "AMPN//"

        return "\n".join([line1, line2, line3, line4, line5])

    @staticmethod
    def _format_dtg(track: Track) -> str:
        """Format the track's timestamp as a Day-Time-Group (``DDHHMMZ``).

        Args:
            track: The track whose ``last_updated`` to format.

        Returns:
            A string like ``"311500Z"``, or ``"UNK"`` if no timestamp.
        """
        if track.last_updated is None:
            return "UNK"
        ts = track.last_updated
        return f"{ts.day:02d}{ts.hour:02d}{ts.minute:02d}Z"
