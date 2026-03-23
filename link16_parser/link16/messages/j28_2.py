"""J28.2 Free Text (US Air Force National Use) decoder.

J28.2 carries free-text communications over the Link 16 network.
This is an extra-credit requirement (REQ-EC-2).

IMPORTANT: The fixed word format for J28.2 is defined in MIL-STD-6016.
Stub implementation until spec is available.
"""

from __future__ import annotations

from link16_parser.core.types import Link16Message, RawJWord

# J28.2: Label=28, Sublabel=2
LABEL = 28
SUBLABEL = 2


class J282FreeTextDecoder:
    """Decodes J28.2 Free Text messages."""

    @property
    def label(self) -> int:
        return LABEL

    @property
    def sublabel(self) -> int:
        return SUBLABEL

    @property
    def msg_type_name(self) -> str:
        return "J28.2 Free Text"

    def decode(self, words: list[RawJWord]) -> Link16Message | None:
        if not words:
            return None

        initial = words[0]

        # TODO: Decode free-text content from J-word data once MIL-STD-6016
        # bit layout for J28.2 is available.
        #
        # Expected: ASCII or similar text encoding within the FWF data bits.

        return Link16Message(
            msg_type="J28.2",
            stn=initial.stn,
            timestamp=initial.timestamp,
            fields={
                "word_count": len(words),
                "raw_words": [w.data for w in words],
                # "text": "...",  # TODO
            },
        )
