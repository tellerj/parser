"""PCAP packet sources: file-based and live pipe.

Reads PCAP data (libpcap format, both endiannesses), strips Ethernet/IP/
UDP|TCP headers, and yields ``(timestamp, payload)`` tuples for downstream
encapsulation decoding. Both classes satisfy the ``PacketSource`` protocol.

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


def _strip_to_transport_payload(frame: bytes) -> bytes | None:
    """Strip Ethernet, IP, and UDP/TCP headers from a raw frame.

    Args:
        frame: A complete captured Ethernet frame (including Ethernet header).

    Returns:
        The transport-layer payload bytes (everything after the UDP or TCP
        header), or ``None`` if the frame is not Ethernet II / IPv4 / UDP|TCP.
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
        return frame[transport_offset + UDP_HEADER_LEN:]

    elif protocol == 6:  # TCP
        if len(frame) < transport_offset + TCP_HEADER_MIN_LEN:
            return None
        tcp_data_offset = (frame[transport_offset + 12] >> 4) * 4
        return frame[transport_offset + tcp_data_offset:]

    return None


class PcapFileSource:
    """Reads packets from a libpcap file on disk.

    Satisfies the ``PacketSource`` protocol.

    Args:
        path: Filesystem path to a ``.pcap`` file.
    """

    def __init__(self, path: str) -> None:
        self._path = path

    def packets(self) -> Iterator[tuple[float, bytes]]:
        """Yield ``(timestamp, payload)`` for every IP packet in the file."""
        with open(self._path, "rb") as f:
            yield from _read_pcap_stream(f)


class PcapPipeSource:
    """Reads packets from a live PCAP stream piped to stdin.

    Satisfies the ``PacketSource`` protocol. Use this when PCAP data is
    piped from ``tcpdump -w -`` or a redirection tunnel.
    """

    def packets(self) -> Iterator[tuple[float, bytes]]:
        """Yield ``(timestamp, payload)`` as packets arrive on stdin."""
        yield from _read_pcap_stream(sys.stdin.buffer)


def _read_pcap_stream(stream: BinaryIO) -> Iterator[tuple[float, bytes]]:
    """Parse a libpcap byte stream and yield ``(timestamp, payload)`` tuples.

    Handles both little-endian (magic ``0xA1B2C3D4``) and big-endian
    (magic ``0xD4C3B2A1``) libpcap files. Reads until EOF or broken pipe.

    Args:
        stream: A readable binary stream positioned at the start of the
            libpcap global header (byte 0 of the file/pipe).

    Yields:
        ``(pcap_timestamp, transport_payload)`` tuples for each valid
        Ethernet/IPv4/UDP|TCP packet. Non-matching packets are skipped.

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

        payload = _strip_to_transport_payload(frame)
        if payload is not None and len(payload) > 0:
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
