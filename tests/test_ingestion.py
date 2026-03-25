"""Tests for PCAP/pcapng parsing, Ethernet/IP frame parsing, and format auto-detection."""

from __future__ import annotations

import io
import os
import tempfile

import pytest

from link16_parser.ingestion import FileSource
from link16_parser.ingestion.pcap_reader import read_pcap_stream
from link16_parser.ingestion.pcapng_reader import read_pcapng_stream
from link16_parser.ingestion.reader import parse_frame

from tests.builders import (
    make_jword,
    make_pcap_file,
    make_pcapng_block,
    make_pcapng_epb,
    make_pcapng_file,
    make_pcapng_idb,
    make_pcapng_shb,
    make_simple_payload,
    make_udp_frame,
)


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

    def test_detects_pcapng(self) -> None:
        payload = make_simple_payload([make_jword()], stn=100)
        frame = make_udp_frame(payload)
        pcapng_bytes = make_pcapng_file([(1700000000.0, frame)])

        path = self._write_tmp(pcapng_bytes)
        try:
            packets = list(FileSource(path).packets())
            assert len(packets) == 1
            ts, p = packets[0]
            assert abs(ts - 1700000000.0) < 0.001
            assert p == payload
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# pcapng reader
# ---------------------------------------------------------------------------


class TestPcapngReader:
    def test_yields_packets(self) -> None:
        payload1 = make_simple_payload([make_jword()], stn=100)
        payload2 = make_simple_payload([make_jword()], stn=200)

        frame1 = make_udp_frame(payload1)
        frame2 = make_udp_frame(payload2)
        data = make_pcapng_file([(1700000000.0, frame1), (1700000001.0, frame2)])

        packets = list(read_pcapng_stream(io.BytesIO(data)))

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

        data = make_pcapng_file([
            (1700000000.0, frame_match1),
            (1700000001.0, frame_skip),
            (1700000002.0, frame_match2),
        ])

        packets = list(read_pcapng_stream(io.BytesIO(data), port_filter=4444))
        assert len(packets) == 2

    def test_timestamp_microseconds(self) -> None:
        """Default resolution (no if_tsresol option) = microseconds."""
        ts = 1700000000.123456
        frame = make_udp_frame(b"test")
        data = make_pcapng_file([(ts, frame)])

        packets = list(read_pcapng_stream(io.BytesIO(data)))
        assert len(packets) == 1
        assert abs(packets[0][0] - ts) < 1e-5

    def test_timestamp_nanoseconds(self) -> None:
        """Explicit if_tsresol=9 means 10^-9 = nanosecond resolution."""
        ts = 1700000000.123456789
        frame = make_udp_frame(b"test")
        data = make_pcapng_file([(ts, frame)], ts_resolution=9)

        packets = list(read_pcapng_stream(io.BytesIO(data)))
        assert len(packets) == 1
        assert abs(packets[0][0] - ts) < 1e-8

    def test_big_endian(self) -> None:
        payload = make_simple_payload([make_jword()], stn=100)
        frame = make_udp_frame(payload)
        data = make_pcapng_file([(1700000000.0, frame)], endian=">")

        packets = list(read_pcapng_stream(io.BytesIO(data)))
        assert len(packets) == 1
        assert abs(packets[0][0] - 1700000000.0) < 0.001
        assert packets[0][1] == payload

    def test_skips_unknown_blocks(self) -> None:
        """Unknown block types between EPBs should be skipped gracefully."""
        payload1 = make_simple_payload([make_jword()], stn=100)
        payload2 = make_simple_payload([make_jword()], stn=200)
        frame1 = make_udp_frame(payload1)
        frame2 = make_udp_frame(payload2)

        # Build manually: SHB + IDB + EPB + unknown block + EPB
        parts = b"".join([
            make_pcapng_shb(),
            make_pcapng_idb(),
            make_pcapng_epb(1700000000.0, frame1),
            make_pcapng_block(0xDEADBEEF, b"mystery payload"),
            make_pcapng_epb(1700000001.0, frame2),
        ])

        packets = list(read_pcapng_stream(io.BytesIO(parts)))
        assert len(packets) == 2

    def test_multiple_interfaces(self) -> None:
        """Two IDBs with different timestamp resolutions."""
        frame1 = make_udp_frame(b"iface0")
        frame2 = make_udp_frame(b"iface1")

        ts = 1700000000.0

        # Interface 0: microsecond (default), Interface 1: nanosecond
        parts = b"".join([
            make_pcapng_shb(),
            make_pcapng_idb(),                          # iface 0, default usec
            make_pcapng_idb(ts_resolution=9),            # iface 1, nanosecond
            make_pcapng_epb(ts, frame1, interface_id=0, ts_divisor=1_000_000),
            make_pcapng_epb(ts, frame2, interface_id=1, ts_divisor=1_000_000_000),
        ])

        packets = list(read_pcapng_stream(io.BytesIO(parts)))
        assert len(packets) == 2
        assert abs(packets[0][0] - ts) < 0.001
        assert abs(packets[1][0] - ts) < 0.001

    def test_rejects_non_ethernet(self) -> None:
        data = b"".join([
            make_pcapng_shb(),
            make_pcapng_idb(link_type=101),  # Raw IP
        ])

        with pytest.raises(ValueError, match="link-layer type 101"):
            list(read_pcapng_stream(io.BytesIO(data)))

    def test_header_prefix(self) -> None:
        """Simulate the auto-detect path: first 4 bytes passed as prefix."""
        payload = make_simple_payload([make_jword()], stn=100)
        frame = make_udp_frame(payload)
        data = make_pcapng_file([(1700000000.0, frame)])

        prefix = data[:4]
        rest = io.BytesIO(data[4:])

        packets = list(read_pcapng_stream(rest, header_prefix=prefix))
        assert len(packets) == 1
        assert packets[0][1] == payload

    def test_timestamp_binary_resolution(self) -> None:
        """if_tsresol with bit 7 set means 2^-n seconds."""
        ts = 1700000000.5
        frame = make_udp_frame(b"test")
        # 0x80 | 20 = use 2^-20 as resolution (~microsecond-scale)
        tsresol_byte = 0x80 | 20
        data = make_pcapng_file([(ts, frame)], ts_resolution=tsresol_byte)

        packets = list(read_pcapng_stream(io.BytesIO(data)))
        assert len(packets) == 1
        assert abs(packets[0][0] - ts) < 1e-5

    def test_empty_file_yields_nothing(self) -> None:
        """SHB + IDB but no EPBs should yield zero packets."""
        data = b"".join([
            make_pcapng_shb(),
            make_pcapng_idb(),
        ])

        packets = list(read_pcapng_stream(io.BytesIO(data)))
        assert len(packets) == 0

    def test_truncated_stream(self) -> None:
        """Stream truncated mid-EPB should yield packets read so far."""
        payload = make_simple_payload([make_jword()], stn=100)
        frame = make_udp_frame(payload)
        data = make_pcapng_file([(1700000000.0, frame), (1700000001.0, frame)])

        # Truncate midway through the second EPB
        truncated = data[: len(data) - 20]

        packets = list(read_pcapng_stream(io.BytesIO(truncated)))
        assert len(packets) == 1
