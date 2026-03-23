"""Tests for PCAP parsing, Ethernet/IP frame parsing, and format auto-detection."""

from __future__ import annotations

import io
import os
import tempfile

import pytest

from link16_parser.ingestion import FileSource
from link16_parser.ingestion.pcap_reader import read_pcap_stream
from link16_parser.ingestion.reader import parse_frame

from tests.builders import make_jword, make_pcap_file, make_simple_payload, make_udp_frame


class TestParseFrame:
    def test_udp(self) -> None:
        payload = b"hello-udp"
        frame = make_udp_frame(payload, src_port=1234, dst_port=5678)

        result = parse_frame(frame)

        assert result is not None
        extracted_payload, src_port, dst_port = result
        assert extracted_payload == payload
        assert src_port == 1234
        assert dst_port == 5678

    def test_rejects_non_ipv4(self) -> None:
        # Build a frame with IPv6 ethertype (0x86DD)
        import struct
        eth_header = b"\x00" * 6 + b"\x00" * 6 + struct.pack("!H", 0x86DD)
        frame = eth_header + b"\x00" * 40  # dummy IPv6

        assert parse_frame(frame) is None

    def test_rejects_short_frame(self) -> None:
        assert parse_frame(b"\x00" * 10) is None

    def test_rejects_non_udp_tcp(self) -> None:
        # Build a valid Ethernet/IPv4 frame but with protocol=47 (GRE)
        import struct
        eth_header = b"\x00" * 6 + b"\x00" * 6 + struct.pack("!H", 0x0800)
        ip_header = bytearray(20)
        ip_header[0] = 0x45  # version=4, IHL=5
        ip_header[9] = 47    # GRE, not UDP or TCP
        frame = eth_header + bytes(ip_header) + b"\x00" * 20

        assert parse_frame(frame) is None


class TestPcapReader:
    def test_yields_packets(self) -> None:
        payload1 = make_simple_payload([make_jword()], stn=100)
        payload2 = make_simple_payload([make_jword()], stn=200)

        frame1 = make_udp_frame(payload1)
        frame2 = make_udp_frame(payload2)
        pcap_bytes = make_pcap_file([(1700000000.0, frame1), (1700000001.0, frame2)])

        stream = io.BytesIO(pcap_bytes)
        packets = list(read_pcap_stream(stream))

        assert len(packets) == 2
        ts1, p1 = packets[0]
        ts2, p2 = packets[1]
        assert abs(ts1 - 1700000000.0) < 0.001
        assert abs(ts2 - 1700000001.0) < 0.001
        assert p1 == payload1
        assert p2 == payload2

    def test_port_filter(self) -> None:
        payload = make_simple_payload([make_jword()], stn=100)

        frame_match1 = make_udp_frame(payload, src_port=4444, dst_port=9999)
        frame_skip = make_udp_frame(payload, src_port=5555, dst_port=6666)
        frame_match2 = make_udp_frame(payload, src_port=9999, dst_port=4444)

        pcap_bytes = make_pcap_file([
            (1700000000.0, frame_match1),
            (1700000001.0, frame_skip),
            (1700000002.0, frame_match2),
        ])

        stream = io.BytesIO(pcap_bytes)
        packets = list(read_pcap_stream(stream, port_filter=4444))

        assert len(packets) == 2


class TestAutoDetect:
    """Test format auto-detection through the public FileSource API."""

    def _write_tmp(self, data: bytes) -> str:
        fd, path = tempfile.mkstemp(suffix=".pcap")
        os.write(fd, data)
        os.close(fd)
        return path

    def test_rejects_garbage(self) -> None:
        path = self._write_tmp(b"\xDE\xAD\xBE\xEF" + b"\x00" * 100)
        try:
            with pytest.raises(ValueError, match="Unrecognized capture format"):
                list(FileSource(path).packets())
        finally:
            os.unlink(path)

    def test_rejects_empty(self) -> None:
        path = self._write_tmp(b"")
        try:
            with pytest.raises(ValueError, match="empty capture input"):
                list(FileSource(path).packets())
        finally:
            os.unlink(path)

    def test_detects_pcap(self) -> None:
        payload = make_simple_payload([make_jword()], stn=100)
        frame = make_udp_frame(payload)
        pcap_bytes = make_pcap_file([(1700000000.0, frame)])

        path = self._write_tmp(pcap_bytes)
        try:
            packets = list(FileSource(path).packets())
            assert len(packets) == 1
        finally:
            os.unlink(path)
