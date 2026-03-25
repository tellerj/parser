"""pcapng format stream reader.

Parses pcapng (PCAP Next Generation) format captures and yields
``(timestamp, payload)`` tuples, same as the libpcap reader.

pcapng is a block-based format defined in:
    https://datatracker.ietf.org/doc/draft-ietf-opsawg-pcapng/

Key differences from libpcap:
    - Block-based structure (Section Header, Interface Description,
      Enhanced Packet, etc.) rather than a flat record stream.
    - Supports multiple capture interfaces in a single file, each with
      its own link-layer type and timestamp resolution.
    - Variable-length options on most block types.

This module is called by the auto-detection logic in ``reader.py`` —
it is not used directly by the rest of the pipeline.
"""

from __future__ import annotations

import logging
import struct
from typing import BinaryIO, Iterator

from link16_parser.ingestion.reader import (
    LINKTYPE_ETHERNET,
    parse_frame,
    read_exact,
)

logger = logging.getLogger(__name__)

# Block type constants
_SHB_TYPE = 0x0A0D0D0A
_IDB_TYPE = 0x00000001
_EPB_TYPE = 0x00000006
_SPB_TYPE = 0x00000003

# Option type constants
_OPT_ENDOFOPT = 0
_OPT_IF_TSRESOL = 9

# Default timestamp resolution when if_tsresol option is absent
_DEFAULT_TSRESOL_BYTE = 6  # 10^-6 = microseconds


def _pad4(n: int) -> int:
    """Round *n* up to the next multiple of 4."""
    return (n + 3) & ~3


def _tsresol_to_divisor(raw_byte: int) -> float:
    """Convert an ``if_tsresol`` option byte to a timestamp divisor.

    Bit 7 selects the base: 0 → power-of-10, 1 → power-of-2.
    Lower 7 bits are the exponent.
    """
    exponent = raw_byte & 0x7F
    if raw_byte & 0x80:
        return float(2 ** exponent)
    return float(10 ** exponent)


def _parse_options(data: bytes, endian: str) -> dict[int, bytes]:
    """Parse pcapng TLV options from *data*.

    Returns a dict mapping option type → raw value bytes.
    Stops at ``opt_endofopt`` (type 0) or when *data* is exhausted.
    Only the first occurrence of each option type is kept.
    """
    options: dict[int, bytes] = {}
    offset = 0
    while offset + 4 <= len(data):
        opt_type, opt_len = struct.unpack_from(f"{endian}HH", data, offset)
        offset += 4
        if opt_type == _OPT_ENDOFOPT:
            break
        if offset + opt_len > len(data):
            break  # truncated option — stop gracefully
        if opt_type not in options:
            options[opt_type] = data[offset:offset + opt_len]
        offset += _pad4(opt_len)
    return options


def read_pcapng_stream(
    stream: BinaryIO,
    port_filter: int | None = None,
    header_prefix: bytes = b"",
) -> Iterator[tuple[float, bytes]]:
    """Parse a pcapng byte stream and yield ``(timestamp, payload)`` tuples.

    Handles both little-endian and big-endian pcapng files, multiple
    interfaces with per-interface timestamp resolution, and gracefully
    skips unknown block types. Reads until EOF or broken pipe.

    Args:
        stream: A readable binary stream. The first bytes of the
            Section Header Block may have already been consumed by
            the auto-detector and passed via ``header_prefix``.
        port_filter: If set, only yield packets where either the source
            or destination port matches. ``None`` means yield all.
        header_prefix: Bytes already read from the stream by the
            auto-detect logic (typically the first 4 bytes containing
            the SHB block type).

    Yields:
        ``(pcap_timestamp, transport_payload)`` tuples for each valid
        Ethernet/IPv4/UDP|TCP packet that passes the port filter.
        Non-matching packets are skipped.

    Raises:
        ValueError: If the SHB is truncated, contains an unrecognized
            byte-order magic, or an IDB specifies a non-Ethernet
            link-layer type.
    """
    # ------------------------------------------------------------------
    # 1. Parse the Section Header Block
    # ------------------------------------------------------------------
    # SHB layout: BlockType(4) + BlockTotalLength(4) + BOM(4) + ...
    # The auto-detect path passes the first 4 bytes (block type) as
    # header_prefix. When called directly, header_prefix is empty and
    # we read the block type ourselves.
    #
    # We need at least 12 bytes (type + length + BOM) to determine
    # endianness, then read the rest of the block.
    shb_needed = 12 - len(header_prefix)
    shb_start = read_exact(stream, shb_needed)
    if shb_start is None:
        raise ValueError(
            "Truncated pcapng input — the file/stream ended before the "
            "Section Header Block could be read."
        )
    shb_fixed = header_prefix + shb_start  # first 12 bytes of SHB

    # Byte-Order Magic is at file offset 8
    bom_le = struct.unpack_from("<I", shb_fixed, 8)[0]
    if bom_le == 0x1A2B3C4D:
        endian = "<"
    elif bom_le == 0x4D3C2B1A:
        endian = ">"
    else:
        raise ValueError(
            f"Unrecognized pcapng byte-order magic: 0x{bom_le:08X}. "
            f"Expected 0x1A2B3C4D or 0x4D3C2B1A."
        )

    # Re-parse Block Total Length at offset 4 with the correct endianness
    block_total_length = struct.unpack_from(f"{endian}I", shb_fixed, 4)[0]
    if block_total_length < 12:
        raise ValueError(
            f"Invalid pcapng SHB block total length: {block_total_length}. "
            f"Minimum is 12 bytes."
        )

    # Read the rest of the SHB (options + trailing length copy)
    shb_remaining = block_total_length - 12
    if shb_remaining > 0:
        rest = read_exact(stream, shb_remaining)
        if rest is None:
            raise ValueError("Truncated pcapng Section Header Block.")

    # ------------------------------------------------------------------
    # 2. Initialize state
    # ------------------------------------------------------------------
    # Each IDB appends its timestamp divisor here; EPBs index by interface_id.
    interfaces: list[float] = []
    packets_read = 0
    packets_yielded = 0

    # ------------------------------------------------------------------
    # 3. Block reading loop
    # ------------------------------------------------------------------
    while True:
        # Read block header: type (4B) + total length (4B)
        block_header = read_exact(stream, 8)
        if block_header is None:
            break  # EOF

        block_type, block_total_length = struct.unpack(
            f"{endian}II", block_header
        )

        if block_total_length < 12:
            raise ValueError(
                f"Invalid pcapng block total length: {block_total_length} "
                f"(block type 0x{block_type:08X}). Minimum is 12 bytes."
            )

        # Read body + trailing length copy
        body_plus_trailer_len = block_total_length - 8
        body_plus_trailer = read_exact(stream, body_plus_trailer_len)
        if body_plus_trailer is None:
            break  # truncated stream — process what we have

        # Body is everything except the trailing 4-byte length copy
        body = body_plus_trailer[:-4]

        # --- IDB (Interface Description Block) ---
        if block_type == _IDB_TYPE:
            if len(body) < 8:
                raise ValueError("Truncated Interface Description Block.")

            link_type = struct.unpack_from(f"{endian}H", body, 0)[0]
            if link_type != LINKTYPE_ETHERNET:
                raise ValueError(
                    f"Unsupported pcapng link-layer type {link_type} on "
                    f"interface {len(interfaces)}. This reader only supports "
                    f"Ethernet captures (type 1). The capture may have been "
                    f"taken on a non-Ethernet interface (e.g. loopback, USB, "
                    f"or a tunnel). Re-capture on an Ethernet interface, or "
                    f"use tcpdump with '-y EN10MB' to force Ethernet framing."
                )

            # Parse options for if_tsresol
            options = _parse_options(body[8:], endian)
            tsresol_data = options.get(_OPT_IF_TSRESOL)
            if tsresol_data is not None and len(tsresol_data) >= 1:
                divisor = _tsresol_to_divisor(tsresol_data[0])
            else:
                divisor = _tsresol_to_divisor(_DEFAULT_TSRESOL_BYTE)

            interfaces.append(divisor)

        # --- EPB (Enhanced Packet Block) ---
        elif block_type == _EPB_TYPE:
            if len(body) < 20:
                logger.warning("Truncated Enhanced Packet Block — skipping")
                continue

            fields = struct.unpack_from(f"{endian}IIIII", body, 0)
            interface_id: int = fields[0]
            ts_high: int = fields[1]
            ts_low: int = fields[2]
            captured_len: int = fields[3]

            if interface_id >= len(interfaces):
                logger.warning(
                    "EPB references interface %d but only %d interfaces "
                    "defined — skipping packet",
                    interface_id, len(interfaces),
                )
                continue

            # Reconstruct 64-bit timestamp and convert to seconds
            raw_ts = (ts_high << 32) | ts_low
            timestamp = raw_ts / interfaces[interface_id]

            # Extract packet data (starts at body offset 20)
            pkt_start = 20
            pkt_end = pkt_start + captured_len
            if pkt_end > len(body):
                logger.warning(
                    "EPB captured_len (%d) exceeds block body — skipping",
                    captured_len,
                )
                continue

            frame = body[pkt_start:pkt_end]
            packets_read += 1

            parsed = parse_frame(frame, port_filter)
            if parsed is None:
                continue

            payload = parsed[0]
            packets_yielded += 1
            yield (timestamp, payload)

        # --- SPB (Simple Packet Block) — skip (no timestamp) ---
        elif block_type == _SPB_TYPE:
            logger.debug("Skipping Simple Packet Block (no timestamp)")

        # --- Another SHB (new section) ---
        elif block_type == _SHB_TYPE:
            raise ValueError(
                "Multi-section pcapng files are not supported. The file "
                "contains a second Section Header Block."
            )

        # --- Unknown block type — skip ---
        else:
            logger.debug(
                "Skipping unknown pcapng block type 0x%08X (%d bytes)",
                block_type, block_total_length,
            )

    # ------------------------------------------------------------------
    # 4. Summary logging
    # ------------------------------------------------------------------
    logger.info(
        "pcapng stream complete: %d packets read, %d matched filter",
        packets_read, packets_yielded,
    )
    if packets_read > 0 and packets_yielded == 0:
        if port_filter is not None:
            logger.warning(
                "No packets matched port filter %d — check --port value",
                port_filter,
            )
        else:
            logger.warning(
                "No valid UDP/TCP IPv4 packets found in capture "
                "(all %d frames were filtered out)",
                packets_read,
            )
