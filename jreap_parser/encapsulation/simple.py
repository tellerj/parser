"""SIMPLE protocol (STANAG 5602) encapsulation decoder.

Fully documented via Wireshark dissector source. This is the recommended
development/test encapsulation since its format is entirely public.

Packet layout:
  - SIMPLE Header (16 bytes): sync 0x49 0x36, length, seq, nodes, type, checksum
  - Link 16 Subheader (18 bytes): subtype, network, NPG, STN, word count, etc.
  - J-words: 10 bytes each (80 bits), little-endian
"""

from __future__ import annotations

import struct
from datetime import datetime, timezone

from jreap_parser.core.types import RawJWord

# SIMPLE sync bytes
SYNC_BYTE_1 = 0x49
SYNC_BYTE_2 = 0x36

SIMPLE_HEADER_LEN = 16
LINK16_SUBHEADER_LEN = 14  # Relevant portion we parse
J_WORD_SIZE = 10  # 80 bits = 10 bytes

# SIMPLE packet types
PACKET_TYPE_LINK16 = 1
PACKET_TYPE_STATUS = 61


class SimpleDecoder:
    """Decodes SIMPLE (STANAG 5602) encapsulated Link 16 packets.

    Validates the sync bytes (``0x49 0x36``), checks for Link 16 packet
    type, parses the Link 16 subheader for NPG/STN/word count, then
    extracts each 10-byte J-word from the payload.
    """

    @property
    def name(self) -> str:
        return "SIMPLE"

    def decode(self, payload: bytes, pcap_timestamp: float) -> list[RawJWord]:
        """Decode a SIMPLE packet into J-words.

        Args:
            payload: UDP payload starting with the SIMPLE header.
            pcap_timestamp: Epoch-seconds timestamp from the PCAP frame.

        Returns:
            List of ``RawJWord`` objects, or empty list if the payload
            is not a valid SIMPLE Link 16 packet.
        """
        if len(payload) < SIMPLE_HEADER_LEN:
            return []

        # Validate sync bytes
        if payload[0] != SYNC_BYTE_1 or payload[1] != SYNC_BYTE_2:
            return []

        packet_type = payload[11]
        if packet_type != PACKET_TYPE_LINK16:
            return []

        # Parse Link 16 subheader (starts after SIMPLE header)
        subheader_offset = SIMPLE_HEADER_LEN
        if len(payload) < subheader_offset + LINK16_SUBHEADER_LEN:
            return []

        subtype = payload[subheader_offset]
        # 0=Uncoded, 1=Coded, 2=Fixed Format
        if subtype not in (0, 1, 2):
            return []

        npg = struct.unpack_from("<H", payload, subheader_offset + 4)[0]
        stn = struct.unpack_from("<H", payload, subheader_offset + 8)[0]
        word_count = struct.unpack_from("<H", payload, subheader_offset + 10)[0]

        ts = datetime.fromtimestamp(pcap_timestamp, tz=timezone.utc)

        # Extract J-words
        words_offset = subheader_offset + LINK16_SUBHEADER_LEN
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
