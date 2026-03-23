"""libpcap format stream reader.

Parses the libpcap (.pcap) capture format and yields
``(timestamp, payload)`` tuples. Handles both endiannesses and both
microsecond and nanosecond timestamp resolution.

This module is called by the auto-detection logic in ``reader.py`` —
it is not used directly by the rest of the pipeline.

Format reference: https://wiki.wireshark.org/Development/LibpcapFileFormat
"""

from __future__ import annotations

import struct
from typing import BinaryIO, Iterator

from link16_parser.ingestion.reader import (
    LINKTYPE_ETHERNET,
    parse_frame,
    read_exact,
)


def read_pcap_stream(
    stream: BinaryIO,
    port_filter: int | None = None,
    header_prefix: bytes = b"",
) -> Iterator[tuple[float, bytes]]:
    """Parse a libpcap byte stream and yield ``(timestamp, payload)`` tuples.

    Handles both little-endian and big-endian libpcap files, with both
    microsecond and nanosecond timestamp resolution. Reads until EOF or
    broken pipe.

    Args:
        stream: A readable binary stream. If ``header_prefix`` is empty,
            the stream must be positioned at byte 0 of the global header.
            Otherwise, the prefix contains the already-consumed leading
            bytes (from auto-detection).
        port_filter: If set, only yield packets where either the source
            or destination port matches. ``None`` means yield all.
        header_prefix: Bytes already read from the stream by the
            auto-detect logic (typically the first 4 bytes containing
            the magic number).

    Yields:
        ``(pcap_timestamp, transport_payload)`` tuples for each valid
        Ethernet/IPv4/UDP|TCP packet that passes the port filter.
        Non-matching packets are skipped.

    Raises:
        ValueError: If the global header is truncated, contains an
            unrecognized magic number, or specifies a non-Ethernet
            link-layer type.
    """
    # Read the rest of the 24-byte global header
    remaining = 24 - len(header_prefix)
    if remaining > 0:
        rest = read_exact(stream, remaining)
        if rest is None:
            raise ValueError(
                "Truncated PCAP input — the file/stream ended before the "
                "24-byte global header could be read. Check that the file "
                "is not empty or corrupted."
            )
        global_header = header_prefix + rest
    else:
        global_header = header_prefix[:24]

    magic = struct.unpack_from("<I", global_header, 0)[0]

    # Microsecond-resolution magic
    if magic == 0xA1B2C3D4:
        endian, ts_divisor = "<", 1_000_000
    elif magic == 0xD4C3B2A1:
        endian, ts_divisor = ">", 1_000_000
    # Nanosecond-resolution magic
    elif magic == 0xA1B23C4D:
        endian, ts_divisor = "<", 1_000_000_000
    elif magic == 0x4D3CB2A1:
        endian, ts_divisor = ">", 1_000_000_000
    else:
        raise ValueError(
            f"Not a recognized PCAP file (magic bytes: 0x{magic:08X}). "
            f"This reader supports libpcap format (.pcap) only — pcapng "
            f"(.pcapng) and other capture formats are not supported. "
            f"If using Wireshark, export as 'Wireshark/tcpdump/... - pcap'."
        )

    # Validate link-layer type (offset 20 in global header)
    link_type = struct.unpack_from(f"{endian}I", global_header, 20)[0]
    if link_type != LINKTYPE_ETHERNET:
        # Common types: 1=Ethernet, 101=Raw IP, 113=Linux cooked, 228=Raw IPv4
        raise ValueError(
            f"Unsupported PCAP link-layer type {link_type}. This reader only "
            f"supports Ethernet captures (type 1). The capture may have been "
            f"taken on a non-Ethernet interface (e.g. loopback, USB, or a "
            f"tunnel). Re-capture on an Ethernet interface, or use tcpdump "
            f"with '-y EN10MB' to force Ethernet framing."
        )

    # Read packet records
    while True:
        # Packet header: 16 bytes (ts_sec, ts_frac, incl_len, orig_len)
        pkt_header = read_exact(stream, 16)
        if pkt_header is None:
            return  # End of stream

        ts_sec, ts_frac, incl_len, _orig_len = struct.unpack(
            f"{endian}IIII", pkt_header
        )
        timestamp = ts_sec + ts_frac / ts_divisor

        frame = read_exact(stream, incl_len)
        if frame is None:
            return

        parsed = parse_frame(frame)
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
