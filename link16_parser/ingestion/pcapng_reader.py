"""pcapng format stream reader (stub).

Parses pcapng (PCAP Next Generation) format captures and yields
``(timestamp, payload)`` tuples, same as the libpcap reader.

pcapng is a block-based format defined in:
    https://www.ietf.org/archive/id/draft-tuexen-opsawg-pcapng-05.html

Key differences from libpcap:
    - Block-based structure (Section Header, Interface Description,
      Enhanced Packet, etc.) rather than a flat record stream.
    - Supports multiple capture interfaces in a single file, each with
      its own link-layer type and timestamp resolution.
    - Variable-length options on most block types.

Status: **stub** — raises ``NotImplementedError`` when called. The
detection logic in ``reader.py`` routes pcapng files here so the error
message is clear about what's missing.
"""

from __future__ import annotations

from typing import BinaryIO, Iterator


def read_pcapng_stream(
    stream: BinaryIO,
    port_filter: int | None = None,
    header_prefix: bytes = b"",
) -> Iterator[tuple[float, bytes]]:
    """Parse a pcapng byte stream and yield ``(timestamp, payload)`` tuples.

    Args:
        stream: A readable binary stream. The first bytes of the
            Section Header Block may have already been consumed by
            the auto-detector and passed via ``header_prefix``.
        port_filter: If set, only yield packets where either the source
            or destination port matches. ``None`` means yield all.
        header_prefix: Bytes already read from the stream by the
            auto-detect logic (typically the first 4 bytes containing
            the SHB block type).

    Raises:
        ValueError: Always — pcapng parsing is not yet implemented.
    """
    raise ValueError(
        "pcapng format detected but not yet supported. To use this "
        "capture, convert it to libpcap format first:\n"
        "  editcap -F pcap input.pcapng output.pcap\n"
        "Or in Wireshark: File > Save As > 'Wireshark/tcpdump/... - pcap'"
    )
