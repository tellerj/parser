"""PCAP packet sources: file-based and live pipe.

Reads PCAP data (libpcap format, both endiannesses), strips Ethernet/IP/
UDP|TCP headers, and yields ``(timestamp, payload)`` tuples for downstream
encapsulation decoding. Both classes satisfy the ``PacketSource`` protocol.

Supports optional port filtering via ``--port`` to skip irrelevant traffic
early in the pipeline (before encapsulation decoding). When no port filter
is set, all UDP/TCP packets are yielded regardless of port number.

Supported frame types:
    - Ethernet II (ethertype 0x0800 = IPv4) only. 802.1Q VLAN tags, IPv6,
      and non-Ethernet link layers are silently skipped.
    - IP protocols: UDP (17), TCP (6). Other protocols are silently skipped.

Not supported:
    - pcapng format (would need a separate reader).
    - Fragmented IP packets (assumes each frame is a complete datagram).
"""

from __future__ import annotations

import struct
import sys
from typing import BinaryIO, Iterator


# Ethernet + IP + UDP/TCP header constants
ETHERNET_HEADER_LEN = 14
IP_HEADER_MIN_LEN = 20
UDP_HEADER_LEN = 8
TCP_HEADER_MIN_LEN = 20


def _parse_frame(frame: bytes) -> tuple[bytes, int, int] | None:
    """Parse an Ethernet/IP/UDP|TCP frame.

    Args:
        frame: A complete captured Ethernet frame (including Ethernet header).

    Returns:
        A tuple of ``(payload, src_port, dst_port)`` where *payload* is the
        transport-layer payload bytes, or ``None`` if the frame is not
        Ethernet II / IPv4 / UDP|TCP.
    """
    if len(frame) < ETHERNET_HEADER_LEN + IP_HEADER_MIN_LEN:
        return None

    # Ethernet: ethertype at offset 12-13
    ethertype = struct.unpack_from("!H", frame, 12)[0]
    if ethertype != 0x0800:  # Not IPv4
        return None

    ip_offset = ETHERNET_HEADER_LEN
    ip_version_ihl = frame[ip_offset]
    ip_header_len = (ip_version_ihl & 0x0F) * 4
    if ip_header_len < IP_HEADER_MIN_LEN:
        return None

    protocol = frame[ip_offset + 9]
    transport_offset = ip_offset + ip_header_len

    if protocol == 17:  # UDP
        if len(frame) < transport_offset + UDP_HEADER_LEN:
            return None
        src_port, dst_port = struct.unpack_from("!HH", frame, transport_offset)
        payload = frame[transport_offset + UDP_HEADER_LEN:]
        return payload, src_port, dst_port

    elif protocol == 6:  # TCP
        if len(frame) < transport_offset + TCP_HEADER_MIN_LEN:
            return None
        src_port, dst_port = struct.unpack_from("!HH", frame, transport_offset)
        tcp_data_offset = (frame[transport_offset + 12] >> 4) * 4
        payload = frame[transport_offset + tcp_data_offset:]
        return payload, src_port, dst_port

    return None


class PcapFileSource:
    """Reads packets from a libpcap file on disk.

    Satisfies the ``PacketSource`` protocol.

    Args:
        path: Filesystem path to a ``.pcap`` file.
        port_filter: If set, only yield packets where either the source
            or destination port matches this value. ``None`` means no
            filtering (yield all UDP/TCP packets).
    """

    def __init__(self, path: str, port_filter: int | None = None) -> None:
        self._path = path
        self._port_filter = port_filter

    def packets(self) -> Iterator[tuple[float, bytes]]:
        """Yield ``(timestamp, payload)`` for every matching IP packet."""
        with open(self._path, "rb") as f:
            yield from _read_pcap_stream(f, self._port_filter)


class PcapPipeSource:
    """Reads packets from a live PCAP stream piped to stdin.

    Satisfies the ``PacketSource`` protocol. Use this when PCAP data is
    piped from ``tcpdump -w -`` or a redirection tunnel.

    Args:
        port_filter: If set, only yield packets where either the source
            or destination port matches this value. ``None`` means no
            filtering (yield all UDP/TCP packets).
    """

    def __init__(self, port_filter: int | None = None) -> None:
        self._port_filter = port_filter

    def packets(self) -> Iterator[tuple[float, bytes]]:
        """Yield ``(timestamp, payload)`` as packets arrive on stdin."""
        yield from _read_pcap_stream(sys.stdin.buffer, self._port_filter)


def _read_pcap_stream(
    stream: BinaryIO,
    port_filter: int | None = None,
) -> Iterator[tuple[float, bytes]]:
    """Parse a libpcap byte stream and yield ``(timestamp, payload)`` tuples.

    Handles both little-endian (magic ``0xA1B2C3D4``) and big-endian
    (magic ``0xD4C3B2A1``) libpcap files. Reads until EOF or broken pipe.

    Args:
        stream: A readable binary stream positioned at the start of the
            libpcap global header (byte 0 of the file/pipe).
        port_filter: If set, only yield packets where either the source
            or destination port matches. ``None`` means yield all.

    Yields:
        ``(pcap_timestamp, transport_payload)`` tuples for each valid
        Ethernet/IPv4/UDP|TCP packet that passes the port filter.
        Non-matching packets are skipped.

    Raises:
        ValueError: If the stream does not start with a valid libpcap
            magic number.
    """
    # Read global header (24 bytes)
    global_header = _read_exact(stream, 24)
    if global_header is None:
        return

    magic = struct.unpack_from("<I", global_header, 0)[0]
    if magic == 0xA1B2C3D4:
        endian = "<"
    elif magic == 0xD4C3B2A1:
        endian = ">"
    else:
        raise ValueError(f"Not a libpcap file (magic: 0x{magic:08X})")

    # Read packet records
    while True:
        # Packet header: 16 bytes (ts_sec, ts_usec, incl_len, orig_len)
        pkt_header = _read_exact(stream, 16)
        if pkt_header is None:
            return  # End of stream

        ts_sec, ts_usec, incl_len, _orig_len = struct.unpack(
            f"{endian}IIII", pkt_header
        )
        timestamp = ts_sec + ts_usec / 1_000_000

        frame = _read_exact(stream, incl_len)
        if frame is None:
            return

        parsed = _parse_frame(frame)
        if parsed is None:
            continue

        payload, src_port, dst_port = parsed
        if len(payload) == 0:
            continue

        # Apply port filter if configured
        if port_filter is not None:
            if src_port != port_filter and dst_port != port_filter:
                continue

        yield (timestamp, payload)


def _read_exact(stream: BinaryIO, n: int) -> bytes | None:
    """Read exactly *n* bytes from a binary stream.

    Args:
        stream: A readable binary stream.
        n: Number of bytes to read.

    Returns:
        Exactly *n* bytes, or ``None`` if the stream reaches EOF before
        *n* bytes are available.
    """
    data = b""
    while len(data) < n:
        chunk = stream.read(n - len(data))
        if not chunk:
            return None
        data += chunk
    return data
