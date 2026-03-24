"""JSON definition-driven message decoder.

Decodes Link 16 messages using field definitions loaded from JSON files.
See ``schema.py`` for the definition format and validation rules.

Bit addressing convention
=========================

``start_bit`` in the JSON is 0-indexed relative to the 57-bit FWF data
portion of each J-word. Bit 0 of FWF data = bit 13 of the full 80-bit
word (bits 0-12 are the header, parsed by ``JWordParser``).

The extraction shifts by ``start_bit + 13`` to reach into the full
10-byte word, consistent with the little-endian convention used by
``parse_jword_header`` in ``parser.py``.
"""

from __future__ import annotations

import logging
from typing import Any

from link16_parser.core.types import (
    Identity,
    Link16Message,
    PlatformId,
    Position,
    RawJWord,
)

logger = logging.getLogger(__name__)

# Offset from FWF-relative bit index to absolute bit index within the
# 80-bit word. The first 13 bits are the header.
_HEADER_BITS = 13


class DefinitionDecoder:
    """Message decoder driven by a JSON field definition.

    Satisfies the ``MessageDecoder`` protocol (``core/interfaces.py``).

    Args:
        definition: A parsed JSON dict containing ``label``, ``sublabel``,
            ``name``, and ``fields``.
    """

    def __init__(self, definition: dict[str, Any]) -> None:
        self._label: int = definition["label"]
        self._sublabel: int = definition["sublabel"]
        self._name: str = definition["name"]
        self._fields: list[dict[str, Any]] = definition["fields"]

    @property
    def label(self) -> int:
        return self._label

    @property
    def sublabel(self) -> int:
        return self._sublabel

    @property
    def msg_type_name(self) -> str:
        return self._name

    def decode(self, words: list[RawJWord]) -> Link16Message | None:
        """Decode J-words into a Link16Message using the field definitions.

        Args:
            words: One or more J-words (initial + continuation/extension).

        Returns:
            A populated ``Link16Message``, or ``None`` if *words* is empty.
        """
        if not words:
            return None

        initial = words[0]
        msg = Link16Message(
            msg_type=self._name,
            stn=initial.stn,
            timestamp=initial.timestamp,
        )

        # Accumulators for frozen composite dataclasses.
        pos_parts: dict[str, float] = {}
        plat_parts: dict[str, str | None] = {}

        for field_def in self._fields:
            word_idx: int = field_def["word"]
            if word_idx >= len(words):
                # Multi-word message but not enough words provided — skip.
                continue

            raw_value = extract_bits(
                words[word_idx].data,
                field_def["start_bit"],
                field_def["length"],
            )

            converted = _convert_value(raw_value, field_def)

            maps_to: str | None = field_def.get("maps_to")
            if maps_to is not None:
                _apply_value(msg, maps_to, converted, pos_parts, plat_parts)

        # Assemble frozen composites from accumulated parts.
        if "lat" in pos_parts and "lon" in pos_parts:
            msg.position = Position(
                lat=pos_parts["lat"],
                lon=pos_parts["lon"],
                alt_m=pos_parts.get("alt_m"),
            )

        if any(v is not None for v in plat_parts.values()):
            msg.platform = PlatformId(
                generic_type=plat_parts.get("generic_type"),
                specific_type=plat_parts.get("specific_type"),
                nationality=plat_parts.get("nationality"),
            )

        return msg


# ---------------------------------------------------------------------------
# Bit extraction
# ---------------------------------------------------------------------------

def extract_bits(word_data: bytes, start_bit: int, length: int) -> int:
    """Extract *length* bits starting at *start_bit* from FWF data.

    *start_bit* is 0-indexed relative to the 57-bit FWF portion.
    The word bytes are interpreted as a single little-endian integer.

    Args:
        word_data: The raw 10-byte J-word.
        start_bit: First bit to extract (0 = first FWF data bit).
        length: Number of bits to extract.

    Returns:
        The extracted unsigned integer value.
    """
    abs_start = start_bit + _HEADER_BITS
    word_int = int.from_bytes(word_data, byteorder="little")
    mask = (1 << length) - 1
    return (word_int >> abs_start) & mask


# ---------------------------------------------------------------------------
# Value conversion
# ---------------------------------------------------------------------------

def _convert_value(raw: int, field_def: dict[str, Any]) -> int | float | str:
    """Apply type-specific conversion to a raw extracted integer."""
    ftype: str = field_def["type"]

    if ftype == "scaled":
        scale: float = float(field_def["scale"])
        offset: float = float(field_def["offset"])
        return raw * scale + offset

    if ftype == "enum":
        values: dict[str, str] = field_def.get("values", {})
        return values.get(str(raw), str(raw))

    # integer, flags, string, track_num — return raw for now.
    # string and track_num conversions will be filled in when the
    # character encoding tables are integrated.
    return raw


# ---------------------------------------------------------------------------
# Value mapping
# ---------------------------------------------------------------------------

# The set of Identity enum values, indexed by their string value for
# fast lookup. Built once at import time.
_IDENTITY_BY_VALUE: dict[str, Identity] = {m.value: m for m in Identity}


def _apply_value(
    msg: Link16Message,
    maps_to: str,
    value: int | float | str,
    pos_parts: dict[str, float],
    plat_parts: dict[str, str | None],
) -> None:
    """Route a converted value to the correct field on the message."""

    # --- Direct attributes ---
    if maps_to == "identity":
        if isinstance(value, str) and value in _IDENTITY_BY_VALUE:
            msg.identity = _IDENTITY_BY_VALUE[value]
        return

    if maps_to == "heading_deg":
        msg.heading_deg = float(value)
        return

    if maps_to == "speed_kph":
        msg.speed_kph = float(value)
        return

    if maps_to == "callsign":
        msg.callsign = str(value)
        return

    if maps_to == "track_number":
        msg.track_number = str(value)
        return

    # --- Composite: position.* ---
    if maps_to.startswith("position."):
        subfield = maps_to[len("position."):]
        pos_parts[subfield] = float(value)
        return

    # --- Composite: platform.* ---
    if maps_to.startswith("platform."):
        subfield = maps_to[len("platform."):]
        plat_parts[subfield] = str(value)
        return

    # --- Overflow: fields.* ---
    if maps_to.startswith("fields."):
        key = maps_to[len("fields."):]
        msg.fields[key] = value
        return

    logger.warning("Unknown maps_to target: %r", maps_to)
