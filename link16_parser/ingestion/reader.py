"""Packet sources with format auto-detection.

Provides ``FileSource`` and ``PipeSource`` — the two ``PacketSource``
implementations that feed the ingestion pipeline. Both auto-detect the
capture format (libpcap or pcapng) from the stream's magic bytes and
delegate to the appropriate format-specific reader.

Frame parsing (Ethernet/IP/UDP|TCP stripping), port filtering, and
stream I/O utilities are shared across all formats and defined here.

Supported capture formats:
    - libpcap (.pcap) — fully implemented in ``pcap_reader.py``.
    - pcapng (.pcapng) — fully implemented in ``pcapng_reader.py``.

Supported frame types:
    - Ethernet II (link-layer type 1, ethertype 0x0800 = IPv4) only.
      802.1Q VLAN tags, IPv6, and non-IPv4 ethertypes are silently skipped.
    - IP protocols: UDP (17), TCP (6). Other protocols are silently skipped.

Timestamps are yielded as epoch-seconds ``float`` values — the raw
capture value with no interpretation. Conversion to ``datetime`` happens
downstream in the encapsulation decoders when constructing ``RawJWord``
objects.

Not supported:
    - Non-Ethernet link layers (raw IP, Linux cooked capture, etc.) —
      raises ``ValueError`` at open time rather than silently misparsing.
    - Fragmented IP packets (assumes each frame is a complete datagram).
"""

from __future__ import annotations

import logging
import struct
import sys
from typing import BinaryIO, Iterator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

# Ethernet + IP + UDP/TCP header constants
ETHERNET_HEADER_LEN = 14
IP_HEADER_MIN_LEN = 20
UDP_HEADER_LEN = 8
TCP_HEADER_MIN_LEN = 20

# libpcap link-layer header type for Ethernet
LINKTYPE_ETHERNET = 1

# Magic numbers for format detection
_PCAP_MAGICS = {
    0xA1B2C3D4,  # libpcap, little-endian, microsecond
    0xD4C3B2A1,  # libpcap, big-endian, microsecond
    0xA1B23C4D,  # libpcap, little-endian, nanosecond
    0x4D3CB2A1,  # libpcap, big-endian, nanosecond
}
_PCAPNG_SHB_BLOCK_TYPE = 0x0A0D0D0A


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def read_exact(stream: BinaryIO, n: int) -> bytes | None:
    """Read exactly *n* bytes from a binary stream.

    Args:
        stream: A readable binary stream.
        n: Number of bytes to read.

    Returns:
        Exactly *n* bytes, or ``None`` if the stream reaches EOF before
        *n* bytes are available.
    """
    buf = bytearray(n)
    pos = 0
    while pos < n:
        chunk = stream.read(n - pos)
        if not chunk:
            return None
        buf[pos:pos + len(chunk)] = chunk
        pos += len(chunk)
    return bytes(buf)


def parse_frame(
    frame: bytes,
    port_filter: int | None = None,
) -> tuple[bytes, int, int] | None:
    """Parse an Ethernet/IP/UDP|TCP frame.

    Args:
        frame: A complete captured Ethernet frame (including Ethernet header).
        port_filter: If set, only return a result when either the source
            or destination port matches. ``None`` means no filtering.

    Returns:
        A tuple of ``(payload, src_port, dst_port)`` where *payload* is the
        transport-layer payload bytes, or ``None`` if the frame is not
        Ethernet II / IPv4 / UDP|TCP, has an empty payload, or does not
        match the port filter.
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

    elif protocol == 6:  # TCP
        if len(frame) < transport_offset + TCP_HEADER_MIN_LEN:
            return None
        src_port, dst_port = struct.unpack_from("!HH", frame, transport_offset)
        tcp_data_offset = (frame[transport_offset + 12] >> 4) * 4
        payload = frame[transport_offset + tcp_data_offset:]

    else:
        return None

    if len(payload) == 0:
        return None

    if port_filter is not None:
        if src_port != port_filter and dst_port != port_filter:
            return None

    return payload, src_port, dst_port


# ---------------------------------------------------------------------------
# Packet source classes (public API)
# ---------------------------------------------------------------------------

class FileSource:
    """Reads packets from a capture file on disk.

    Auto-detects the capture format (libpcap or pcapng) from the file's
    magic bytes. Satisfies the ``PacketSource`` protocol.

    Args:
        path: Filesystem path to a capture file (``.pcap`` or ``.pcapng``).
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
            yield from _auto_detect_stream(f, self._port_filter)


class PipeSource:
    """Reads packets from a live capture stream piped to stdin.

    Auto-detects the capture format from the stream's magic bytes.
    Satisfies the ``PacketSource`` protocol. Use this when capture data
    is piped from ``tcpdump -w -`` or a redirection tunnel.

    Args:
        port_filter: If set, only yield packets where either the source
            or destination port matches this value. ``None`` means no
            filtering (yield all UDP/TCP packets).
    """

    def __init__(self, port_filter: int | None = None) -> None:
        self._port_filter = port_filter

    def packets(self) -> Iterator[tuple[float, bytes]]:
        """Yield ``(timestamp, payload)`` as packets arrive on stdin."""
        yield from _auto_detect_stream(sys.stdin.buffer, self._port_filter)


# ---------------------------------------------------------------------------
# Format auto-detection
# ---------------------------------------------------------------------------

def _auto_detect_stream(
    stream: BinaryIO,
    port_filter: int | None = None,
) -> Iterator[tuple[float, bytes]]:
    """Detect capture format from magic bytes and delegate to the right reader.

    Reads the first 4 bytes of the stream to determine the format, then
    passes those bytes (as ``header_prefix``) to the format-specific
    reader so they aren't lost.

    Args:
        stream: A readable binary stream positioned at byte 0.
        port_filter: Passed through to the format-specific reader.

    Raises:
        ValueError: If the stream is empty, has unrecognized magic bytes,
            or the detected format is not yet supported (e.g. pcapng).
    """
    magic_bytes = read_exact(stream, 4)
    if magic_bytes is None:
        raise ValueError(
            "Truncated or empty capture input — the file/stream ended before "
            "the magic bytes could be read. Check that the file exists and "
            "is not empty, or that the pipe source is producing data."
        )

    magic = struct.unpack_from("<I", magic_bytes, 0)[0]

    if magic in _PCAP_MAGICS:
        from link16_parser.ingestion.pcap_reader import read_pcap_stream
        yield from read_pcap_stream(stream, port_filter, header_prefix=magic_bytes)
    elif magic == _PCAPNG_SHB_BLOCK_TYPE:
        from link16_parser.ingestion.pcapng_reader import read_pcapng_stream
        yield from read_pcapng_stream(stream, port_filter, header_prefix=magic_bytes)
    else:
        raise ValueError(
            f"Unrecognized capture format (magic bytes: 0x{magic:08X}). "
            f"Supported formats: libpcap (.pcap) and pcapng (.pcapng). "
            f"If this is a different format, convert it first:\n"
            f"  editcap -F pcap input_file output.pcap"
        )
