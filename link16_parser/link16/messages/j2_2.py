"""J2.2 Air PPLI (Precise Participant Location and Identification) decoder.

J2.2 is transmitted by Link 16 air participants to convey their own position
and identity. This is the primary source of air participant position data.

Contents (per open literature):
  - Voice callsign
  - Position (lat/lon)
  - Altitude
  - Course/heading
  - Speed
  - IFF codes (Mode 1-4)
  - Air platform type (generic)
  - Air platform activity

IMPORTANT: The exact bit positions for each field within the 70-bit data
portion are defined in MIL-STD-6016 (Distribution C restricted). This
decoder will be completed once that spec is available. For now, it extracts
the J-word envelope and produces a message with placeholder field values.
"""

from __future__ import annotations

from link16_parser.core.types import Link16Message, RawJWord

# J2.2: Label=2, Sublabel=2
LABEL = 2
SUBLABEL = 2


class J22AirPpliDecoder:
    """Decodes J2.2 Air PPLI messages."""

    @property
    def label(self) -> int:
        return LABEL

    @property
    def sublabel(self) -> int:
        return SUBLABEL

    @property
    def msg_type_name(self) -> str:
        return "J2.2 Air PPLI"

    def decode(self, words: list[RawJWord]) -> Link16Message | None:
        if not words:
            return None

        initial = words[0]

        # TODO: Decode field-level data from the 70-bit FWF data portion
        # once MIL-STD-6016 bit layouts are available.
        #
        # Expected fields to extract:
        #   - Latitude/Longitude (from extension/continuation words)
        #   - Altitude
        #   - Course/heading
        #   - Speed
        #   - Voice callsign
        #   - Air platform type (generic: fighter, bomber, etc.)
        #   - IFF codes

        return Link16Message(
            msg_type="J2.2",
            stn=initial.stn,
            timestamp=initial.timestamp,
            # position=Position(lat=..., lon=..., alt_m=...),  # TODO
            # heading_deg=...,  # TODO
            # speed_kph=...,  # TODO
            # callsign=...,  # TODO
            # platform=PlatformId(generic_type=..., nationality=...),  # TODO
            fields={"word_count": len(words), "raw_words": [w.data for w in words]},
        )
