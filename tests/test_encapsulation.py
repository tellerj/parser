"""Tests for encapsulation decoders: SIMPLE, SISO-J, Auto, and JREAP-C stub."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from link16_parser.encapsulation.detect import AutoDecoder
from link16_parser.encapsulation.jreap_c import JreapCDecoder
from link16_parser.encapsulation.simple import SimpleDecoder
from link16_parser.encapsulation.siso_j import SisoJDecoder

from tests.builders import make_jword, make_simple_payload, make_siso_j_payload

PCAP_TS = 1_700_000_000.0
EXPECTED_DT = datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)


class TestSimpleDecoder:
    def test_extracts_jwords(self) -> None:
        jw1 = make_jword(label=2, sublabel=2)
        jw2 = make_jword(label=3, sublabel=2)
        payload = make_simple_payload([jw1, jw2], stn=150, npg=7)

        words = SimpleDecoder().decode(payload, PCAP_TS)

        assert len(words) == 2
        assert words[0].stn == 150
        assert words[0].npg == 7
        assert words[0].data == jw1
        assert words[1].data == jw2
        assert words[0].timestamp == EXPECTED_DT

    def test_rejects_wrong_sync(self) -> None:
        payload = bytearray(make_simple_payload([make_jword()], stn=100))
        payload[0] = 0xFF  # corrupt sync byte

        words = SimpleDecoder().decode(bytes(payload), PCAP_TS)
        assert words == []

    def test_rejects_non_link16_type(self) -> None:
        payload = bytearray(make_simple_payload([make_jword()], stn=100))
        payload[11] = 61  # status packet, not Link 16

        words = SimpleDecoder().decode(bytes(payload), PCAP_TS)
        assert words == []


class TestSisoJDecoder:
    def test_extracts_jwords(self) -> None:
        jw = make_jword(label=2, sublabel=2)
        payload = make_siso_j_payload([jw], stn=200, npg=5)

        words = SisoJDecoder().decode(payload, PCAP_TS)

        assert len(words) == 1
        assert words[0].stn == 200
        assert words[0].npg == 5
        assert words[0].data == jw
        assert words[0].timestamp == EXPECTED_DT

    def test_rejects_wrong_pdu_type(self) -> None:
        payload = bytearray(make_siso_j_payload([make_jword()], stn=100))
        payload[2] = 1  # Entity State PDU, not Signal

        words = SisoJDecoder().decode(bytes(payload), PCAP_TS)
        assert words == []

    def test_rejects_wrong_tdl_type(self) -> None:
        payload = bytearray(make_siso_j_payload([make_jword()], stn=100))
        # TDL type is at offset 12 (DIS header) + 10 (Signal PDU field) = 22, big-endian
        payload[22] = 0
        payload[23] = 99  # not Link 16 (100)

        words = SisoJDecoder().decode(bytes(payload), PCAP_TS)
        assert words == []


class TestAutoDecoder:
    def test_routes_simple(self) -> None:
        payload = make_simple_payload([make_jword()], stn=100)
        words = AutoDecoder().decode(payload, PCAP_TS)

        assert len(words) == 1
        assert words[0].stn == 100

    def test_routes_siso_j(self) -> None:
        payload = make_siso_j_payload([make_jword()], stn=200)
        words = AutoDecoder().decode(payload, PCAP_TS)

        assert len(words) == 1
        assert words[0].stn == 200

    def test_empty_payload_returns_empty(self) -> None:
        words = AutoDecoder().decode(b"", PCAP_TS)
        assert words == []


# ---------------------------------------------------------------------------
# xfail stub for JREAP-C
# ---------------------------------------------------------------------------

class TestJreapCDecoder:
    @pytest.mark.xfail(reason="JREAP-C awaiting MIL-STD-3011", strict=True)
    def test_decodes_jreap_c_payload(self) -> None:
        # When JREAP-C is implemented, this test should construct a valid
        # JREAP-C payload and assert non-empty RawJWord output.
        # For now, any non-empty input returns empty (stub behavior).
        dummy_payload = b"\x00" * 100
        words = JreapCDecoder().decode(dummy_payload, PCAP_TS)
        assert len(words) > 0
