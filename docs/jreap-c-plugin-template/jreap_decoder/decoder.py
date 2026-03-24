"""JREAP-C (MIL-STD-3011) encapsulation decoder.

This module strips JREAP-C transport headers from UDP payloads to extract
raw Link 16 J-words. It is loaded as a plugin by the link16-parser tool.

Activation:
    python -m link16_parser --file capture.pcap --encap-plugin jreap_decoder.decoder

Reference implementation:
    See link16_parser/encapsulation/simple.py for a complete working example
    of the same pattern (STANAG 5602 / SIMPLE encapsulation).
"""

from __future__ import annotations

import struct
from datetime import datetime, timezone

from link16_parser.core.interfaces import EncapsulationDecoder
from link16_parser.core.types import RawJWord

# ---------------------------------------------------------------------------
# Header sizes — FILL THESE IN from MIL-STD-3011
#
# These are the byte lengths of each header section in a JREAP-C packet.
# Look for the header format tables in the spec.
# ---------------------------------------------------------------------------

TBH_LEN = 0           # TODO: Transmission Block Header length in bytes
MGH_LEN = 0           # TODO: Message Group Header length in bytes
APP_HEADER_LEN = 0    # TODO: Application Header length in bytes

MIN_PACKET_LEN = TBH_LEN + MGH_LEN + APP_HEADER_LEN

# ---------------------------------------------------------------------------
# Field offsets within each header — FILL THESE IN from MIL-STD-3011
#
# These are byte offsets relative to the START of each header section.
# Use struct format characters to match the field width and endianness.
# Common formats: "<H" = little-endian uint16, "<I" = little-endian uint32,
#                 ">H" = big-endian uint16.
# ---------------------------------------------------------------------------

# TBH validation: magic bytes, version field, or other identifier that
# distinguishes JREAP-C from other packet types. Used to return [] early
# for non-JREAP-C payloads (critical for auto-detection).
#
# TODO: What byte(s) identify a JREAP-C packet? Fill in below.
# TBH_MAGIC_OFFSET = ??
# TBH_MAGIC_VALUE = ??

# MGH field offsets (relative to start of MGH):
MGH_NPG_OFFSET = 0    # TODO: byte offset of NPG within the MGH
MGH_NPG_FORMAT = "<H"  # TODO: struct format for NPG (e.g., "<H" for LE uint16)

# Application Header field offsets (relative to start of App Header):
APP_STN_OFFSET = 0         # TODO: byte offset of STN within the App Header
APP_STN_FORMAT = "<H"       # TODO: struct format for STN
APP_WORD_COUNT_OFFSET = 0  # TODO: byte offset of word count within the App Header
APP_WORD_COUNT_FORMAT = "<H"  # TODO: struct format for word count

J_WORD_SIZE = 10  # 80 bits = 10 bytes — this is standard Link 16, don't change


class JreapCDecoder:
    """Decodes JREAP-C (MIL-STD-3011) encapsulated Link 16 packets.

    Strips the JREAP-C transport headers (TBH, MGH, Application Headers)
    and extracts the raw 10-byte J-words from the payload.
    """

    @property
    def name(self) -> str:
        # Must return exactly "JREAP-C" — do not change this value.
        return "JREAP-C"

    def decode(self, payload: bytes, pcap_timestamp: float) -> list[RawJWord]:
        """Decode a JREAP-C packet into J-words.

        Args:
            payload: Raw UDP payload bytes (IP/UDP headers already stripped).
            pcap_timestamp: Epoch-seconds timestamp from the PCAP frame.

        Returns:
            List of RawJWord objects, or empty list if the payload is not
            valid JREAP-C. Never raises exceptions for malformed input.
        """

        # --- 1. Length validation ---
        if len(payload) < MIN_PACKET_LEN:
            return []

        # --- 2. TBH validation ---
        # TODO: Check magic bytes / version / packet type that identify
        # JREAP-C packets. This is critical — without it, auto-detection
        # will false-positive on non-JREAP-C payloads.
        #
        # Example:
        #   if payload[TBH_MAGIC_OFFSET] != TBH_MAGIC_VALUE:
        #       return []

        # --- 3. Parse MGH (starts after TBH) ---
        mgh_offset = TBH_LEN
        npg = struct.unpack_from(MGH_NPG_FORMAT, payload, mgh_offset + MGH_NPG_OFFSET)[0]

        # --- 4. Parse Application Header (starts after MGH) ---
        app_offset = mgh_offset + MGH_LEN
        stn = struct.unpack_from(APP_STN_FORMAT, payload, app_offset + APP_STN_OFFSET)[0]
        word_count = struct.unpack_from(
            APP_WORD_COUNT_FORMAT, payload, app_offset + APP_WORD_COUNT_OFFSET,
        )[0]

        # --- 5. Timestamp ---
        ts = datetime.fromtimestamp(pcap_timestamp, tz=timezone.utc)

        # --- 6. Extract J-words ---
        words_offset = app_offset + APP_HEADER_LEN
        words: list[RawJWord] = []

        for i in range(word_count):
            start = words_offset + i * J_WORD_SIZE
            end = start + J_WORD_SIZE
            if end > len(payload):
                break
            words.append(RawJWord(
                data=payload[start:end],
                stn=stn,
                npg=npg,
                timestamp=ts,
            ))

        return words


# Type check: pyright will flag an error here if the class doesn't
# satisfy the EncapsulationDecoder protocol.
_: EncapsulationDecoder = JreapCDecoder()
