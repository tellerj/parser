"""Tests for the JREAP-C encapsulation decoder.

Each test constructs a known JREAP-C payload and verifies the decoder
extracts the correct J-words with the right metadata.

Reference: tests/test_encapsulation.py in the link16-parser repo shows
the same pattern for SIMPLE and SISO-J decoders.
"""

from __future__ import annotations

import struct
from datetime import datetime, timezone

from link16_parser.core.types import RawJWord

from jreap_decoder.decoder import (
    APP_HEADER_LEN,
    APP_STN_FORMAT,
    APP_STN_OFFSET,
    APP_WORD_COUNT_FORMAT,
    APP_WORD_COUNT_OFFSET,
    MGH_LEN,
    MGH_NPG_FORMAT,
    MGH_NPG_OFFSET,
    TBH_LEN,
    JreapCDecoder,
)

PCAP_TS = 1_700_000_000.0
EXPECTED_DT = datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_jword(fill: int = 0x00) -> bytes:
    """Build a minimal 10-byte J-word for testing.

    The encapsulation decoder doesn't parse J-word contents, only extracts
    them, so any 10 bytes will do.
    """
    return bytes([fill]) * 10


def _make_jreap_c_payload(
    jwords: list[bytes],
    stn: int = 100,
    npg: int = 7,
) -> bytes:
    """Build a synthetic JREAP-C packet containing the given J-words.

    Constructs valid TBH + MGH + Application Header + J-word data.
    This mirrors the real wire format so tests validate the decoder
    against known byte sequences.

    Args:
        jwords: List of 10-byte J-word payloads.
        stn: Source Track Number to embed in the header.
        npg: Network Participation Group to embed in the header.

    Returns:
        Complete JREAP-C UDP payload bytes.
    """
    # --- TBH ---
    # TODO: Construct a valid TBH from MIL-STD-3011.
    # Must include whatever magic/version bytes the decoder checks.
    tbh = bytearray(TBH_LEN)
    # Example: tbh[MAGIC_OFFSET] = MAGIC_VALUE

    # --- MGH ---
    # TODO: Construct a valid MGH with the NPG embedded.
    mgh = bytearray(MGH_LEN)
    struct.pack_into(MGH_NPG_FORMAT, mgh, MGH_NPG_OFFSET, npg)

    # --- Application Header ---
    # TODO: Construct a valid App Header with STN and word count.
    app = bytearray(APP_HEADER_LEN)
    struct.pack_into(APP_STN_FORMAT, app, APP_STN_OFFSET, stn)
    struct.pack_into(APP_WORD_COUNT_FORMAT, app, APP_WORD_COUNT_OFFSET, len(jwords))

    return bytes(tbh) + bytes(mgh) + bytes(app) + b"".join(jwords)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestJreapCDecoder:
    def test_name(self) -> None:
        assert JreapCDecoder().name == "JREAP-C"

    def test_extracts_single_jword(self) -> None:
        jw = _make_jword(fill=0xAB)
        payload = _make_jreap_c_payload([jw], stn=150, npg=7)

        words = JreapCDecoder().decode(payload, PCAP_TS)

        assert len(words) == 1
        assert words[0].stn == 150
        assert words[0].npg == 7
        assert words[0].data == jw
        assert words[0].timestamp == EXPECTED_DT

    def test_extracts_multiple_jwords(self) -> None:
        jw1 = _make_jword(fill=0x11)
        jw2 = _make_jword(fill=0x22)
        payload = _make_jreap_c_payload([jw1, jw2], stn=200, npg=5)

        words = JreapCDecoder().decode(payload, PCAP_TS)

        assert len(words) == 2
        assert words[0].data == jw1
        assert words[1].data == jw2
        assert words[0].stn == 200
        assert words[1].npg == 5

    def test_rejects_too_short_payload(self) -> None:
        words = JreapCDecoder().decode(b"\x00" * 5, PCAP_TS)
        assert words == []

    def test_rejects_non_jreap_c_payload(self) -> None:
        """Payload that doesn't match JREAP-C format returns empty list.

        TODO: This test depends on the TBH validation check in decode().
        Construct a payload that has wrong magic/version bytes.
        """
        # Build a payload with correct length but wrong header values
        garbage = b"\xDE\xAD\xBE\xEF" + b"\x00" * 200
        words = JreapCDecoder().decode(garbage, PCAP_TS)
        assert words == []

    def test_truncated_jword_is_skipped(self) -> None:
        """If payload ends mid-jword, only complete words are extracted."""
        jw = _make_jword()
        payload = _make_jreap_c_payload([jw], stn=100)
        # Chop off last 3 bytes so the J-word is incomplete
        truncated = payload[:-3]

        words = JreapCDecoder().decode(truncated, PCAP_TS)
        assert words == []

    def test_empty_payload(self) -> None:
        words = JreapCDecoder().decode(b"", PCAP_TS)
        assert words == []

    def test_zero_jwords(self) -> None:
        """A valid packet with zero J-words returns an empty list."""
        payload = _make_jreap_c_payload([], stn=100)
        words = JreapCDecoder().decode(payload, PCAP_TS)
        assert words == []
