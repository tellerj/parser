"""DIS Signal PDU / SISO-J (SISO-STD-002-2021) encapsulation decoder.

Used in simulation environments. Encapsulates Link 16 in DIS Signal PDUs
over UDP. Format is fully documented in SISO-STD-002-2021.

Layout:
  - DIS PDU Header (12 bytes)
  - Signal PDU fields (Radio Reference ID, Encoding, TDL Type, Data Length, etc.)
  - Link 16 Simulation Network Header (20 bytes)
  - J-words (10 bytes each)
"""

from __future__ import annotations

import struct
from datetime import datetime, timezone

from jreap_parser.core.types import RawJWord

# DIS constants
DIS_SIGNAL_PDU_TYPE = 26
TDL_TYPE_LINK16 = 100

# Offsets within the DIS PDU (after the 12-byte DIS header)
# Signal PDU specific fields start at offset 12
DIS_HEADER_LEN = 12
SIGNAL_PDU_FIELDS_LEN = 20  # Radio Ref ID(6) + RadioNum(2) + Encoding(2) + TDL(2) + SampleRate(4) + DataLen(2) + Samples(2)
LINK16_SIM_HEADER_LEN = 20  # 160 bits

# Message type identifiers (SISO-STD-002 Table 6)
MSG_TYPE_JTIDS_HEADER_MESSAGES = 0
MSG_TYPE_JTIDS_LET = 6

J_WORD_SIZE = 10
JTIDS_HEADER_WORD_SIZE = 6  # 48 bits padded to 6 bytes


class SisoJDecoder:
    """Decodes DIS Signal PDU encapsulated Link 16 packets (SISO-STD-002).

    Validates the DIS PDU type (Signal = 26) and TDL type (Link 16 = 100),
    parses the Link 16 Simulation Network Header for NPG and message type,
    extracts the STN from the JTIDS Header Word (for message type 0),
    then extracts each 10-byte J-word from the data portion.
    """

    @property
    def name(self) -> str:
        return "SISO-J"

    def decode(self, payload: bytes, pcap_timestamp: float) -> list[RawJWord]:
        """Decode a DIS Signal PDU into J-words.

        Args:
            payload: UDP payload starting with the DIS PDU header.
            pcap_timestamp: Epoch-seconds timestamp from the PCAP frame.

        Returns:
            List of ``RawJWord`` objects, or empty list if the payload
            is not a valid DIS Link 16 Signal PDU.
        """
        min_len = DIS_HEADER_LEN + SIGNAL_PDU_FIELDS_LEN + LINK16_SIM_HEADER_LEN
        if len(payload) < min_len:
            return []

        # DIS header: check PDU type at offset 2
        pdu_type = payload[2]
        if pdu_type != DIS_SIGNAL_PDU_TYPE:
            return []

        # Signal PDU: TDL Type at offset 12 + 10 (after Radio Ref ID + RadioNum + Encoding)
        tdl_offset = DIS_HEADER_LEN + 10
        tdl_type = struct.unpack_from("!H", payload, tdl_offset)[0]
        if tdl_type != TDL_TYPE_LINK16:
            return []

        # Data length in bits at offset 12 + 14
        data_len_bits = struct.unpack_from("!H", payload, DIS_HEADER_LEN + 14)[0]

        # Link 16 Simulation Network Header starts after Signal PDU fields
        sim_header_offset = DIS_HEADER_LEN + SIGNAL_PDU_FIELDS_LEN
        npg = struct.unpack_from("!H", payload, sim_header_offset)[0]
        msg_type_id = payload[sim_header_offset + 5]

        # We handle Message Type 0 (JTIDS Header + J-words) and 6 (LET)
        if msg_type_id not in (MSG_TYPE_JTIDS_HEADER_MESSAGES, MSG_TYPE_JTIDS_LET):
            return []

        # Data portion starts after the Link 16 Sim Network Header
        data_offset = sim_header_offset + LINK16_SIM_HEADER_LEN

        # For type 0: first 6 bytes are the JTIDS Header Word (contains STN)
        stn = 0
        j_words_start = data_offset

        if msg_type_id == MSG_TYPE_JTIDS_HEADER_MESSAGES:
            if len(payload) < data_offset + JTIDS_HEADER_WORD_SIZE:
                return []
            # STN is bits 4-18 of the 48-bit header word (big-endian in v2.0)
            header_word = struct.unpack_from("!Q", payload + b"\x00\x00", data_offset)[0] >> 16
            stn = (header_word >> 4) & 0x7FFF
            j_words_start = data_offset + JTIDS_HEADER_WORD_SIZE

        ts = datetime.fromtimestamp(pcap_timestamp, tz=timezone.utc)

        # Extract J-words
        remaining = len(payload) - j_words_start
        word_count = remaining // J_WORD_SIZE
        words: list[RawJWord] = []

        for i in range(word_count):
            start = j_words_start + i * J_WORD_SIZE
            end = start + J_WORD_SIZE
            words.append(RawJWord(
                data=payload[start:end],
                stn=stn,
                npg=npg,
                timestamp=ts,
            ))

        return words
