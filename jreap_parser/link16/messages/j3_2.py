"""J3.2 Air Track (Surveillance) decoder.

J3.2 messages carry surveillance track information for air contacts,
typically transmitted by C2 platforms (E-3 AWACS, E-2 Hawkeye).

Contents (per open literature):
  - Track number (5-character alphanumeric)
  - Strength (number of aircraft)
  - Position (lat/lon)
  - Speed
  - Course/heading
  - Identity (pending/unknown/assumed friend/friend/neutral/suspect/hostile)
  - Air platform type (generic category + specific type)

IMPORTANT: Exact bit positions require MIL-STD-6016. Stub implementation.
"""

from __future__ import annotations

from jreap_parser.core.types import Link16Message, RawJWord

# J3.2: Label=3, Sublabel=2
LABEL = 3
SUBLABEL = 2


class J32AirTrackDecoder:
    """Decodes J3.2 Air Track surveillance messages."""

    @property
    def label(self) -> int:
        return LABEL

    @property
    def sublabel(self) -> int:
        return SUBLABEL

    @property
    def msg_type_name(self) -> str:
        return "J3.2 Air Track"

    def decode(self, words: list[RawJWord]) -> Link16Message | None:
        if not words:
            return None

        initial = words[0]

        # TODO: Decode field-level data once MIL-STD-6016 is available.
        #
        # Expected fields to extract:
        #   - Track number (5-char alphanumeric)
        #   - Strength (number of aircraft)
        #   - Latitude/Longitude
        #   - Speed
        #   - Course/heading
        #   - Identity (friend/hostile/neutral/etc.)
        #   - Air platform type (generic + specific, e.g. FTR / F-16C)

        return Link16Message(
            msg_type="J3.2",
            stn=initial.stn,
            timestamp=initial.timestamp,
            # position=Position(lat=..., lon=..., alt_m=...),  # TODO
            # identity=Identity.UNKNOWN,  # TODO
            # heading_deg=...,  # TODO
            # speed_kph=...,  # TODO
            # platform=PlatformId(generic_type=..., specific_type=..., nationality=...),  # TODO
            fields={"word_count": len(words), "raw_words": [w.data for w in words]},
        )
