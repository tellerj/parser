"""Synthetic test data builders for the link16-parser pipeline.

Every function is pure, takes explicit parameters with sensible defaults,
and returns ``bytes``. They compose bottom-up: J-word → encapsulation
payload → UDP frame → PCAP file. No project imports — only ``struct``.

Every byte produced is traceable to the format spec so that test failures
are debuggable without opaque fixture files.
"""

from __future__ import annotations

import struct


# ---------------------------------------------------------------------------
# J-word builders
# ---------------------------------------------------------------------------

def make_jword_header(
    word_format: int = 0,
    label: int = 2,
    sublabel: int = 2,
    mli: int = 0,
) -> int:
    """Return the 16-bit little-endian header value for a J-word.

    Bit layout (matches ``link16/parser.py`` masks):
        bits 0-1:   word_format (0=INITIAL, 1=CONTINUATION, 2=EXTENSION)
        bits 2-6:   label (0-31)
        bits 7-9:   sublabel (0-7)
        bits 10-12: mli (0-7)
    """
    return (
        (word_format & 0x3)
        | ((label & 0x1F) << 2)
        | ((sublabel & 0x7) << 7)
        | ((mli & 0x7) << 10)
    )


def make_jword(
    word_format: int = 0,
    label: int = 2,
    sublabel: int = 2,
    mli: int = 0,
    payload_fill: int = 0x00,
) -> bytes:
    """Build a 10-byte J-word with the given header fields.

    First 2 bytes are the LE-encoded header. Remaining 8 bytes are
    filled with *payload_fill*.
    """
    header_val = make_jword_header(word_format, label, sublabel, mli)
    return struct.pack("<H", header_val) + bytes([payload_fill] * 8)


def make_jword_with_data(
    word_format: int = 0,
    label: int = 2,
    sublabel: int = 2,
    mli: int = 0,
    data_bits: dict[int, tuple[int, int]] | None = None,
) -> bytes:
    """Build a 10-byte J-word with specific bits set in the FWF data.

    Like ``make_jword``, but allows setting individual bit ranges in
    the 57-bit FWF data portion (bits 13-69 of the 80-bit word).

    Args:
        word_format: Word format field (bits 0-1).
        label: Label field (bits 2-6).
        sublabel: Sublabel field (bits 7-9).
        mli: Message Length Indicator (bits 10-12).
        data_bits: Mapping of ``{start_bit: (length, value)}`` where
            *start_bit* is 0-indexed relative to the FWF data portion
            (bit 0 = bit 13 of the full word). Each *(length, value)*
            pair is OR'd into the word at the specified position.

    Returns:
        A 10-byte J-word with the header and requested data bits set.
    """
    header_val = make_jword_header(word_format, label, sublabel, mli)

    # Start with a zeroed 80-bit word, set the header.
    word_int = header_val  # bits 0-15 (only 0-12 meaningful)

    if data_bits:
        for start_bit, (length, value) in data_bits.items():
            abs_start = start_bit + 13  # skip header
            mask = (1 << length) - 1
            word_int |= (value & mask) << abs_start

    return word_int.to_bytes(10, byteorder="little")


# ---------------------------------------------------------------------------
# SIMPLE encapsulation builder
# ---------------------------------------------------------------------------

def make_simple_payload(
    jwords: list[bytes],
    stn: int = 100,
    npg: int = 7,
    subtype: int = 0,
) -> bytes:
    """Build a SIMPLE (STANAG 5602) encapsulated UDP payload.

    Layout: 16-byte SIMPLE header + 14-byte Link 16 subheader + J-words.
    Offsets match ``encapsulation/simple.py``.
    """
    word_count = len(jwords)

    # SIMPLE header (16 bytes)
    header = bytearray(16)
    header[0] = 0x49   # sync byte 1
    header[1] = 0x36   # sync byte 2
    header[11] = 1     # packet_type = LINK16

    # Link 16 subheader (14 bytes)
    subheader = bytearray(14)
    subheader[0] = subtype
    struct.pack_into("<H", subheader, 4, npg)
    struct.pack_into("<H", subheader, 8, stn)
    struct.pack_into("<H", subheader, 10, word_count)

    return bytes(header) + bytes(subheader) + b"".join(jwords)


# ---------------------------------------------------------------------------
# DIS / SISO-J encapsulation builder
# ---------------------------------------------------------------------------

def make_siso_j_payload(
    jwords: list[bytes],
    stn: int = 100,
    npg: int = 7,
    msg_type_id: int = 0,
) -> bytes:
    """Build a DIS Signal PDU / SISO-J encapsulated UDP payload.

    Layout: 12-byte DIS header + 20-byte Signal PDU fields + 20-byte
    Link 16 sim network header + 6-byte JTIDS header (if msg_type_id==0)
    + J-words. Offsets match ``encapsulation/siso_j.py``.

    The STN encoding must invert the production extraction::

        header_word = struct.unpack_from("!Q", payload + b"\\x00\\x00", off)[0] >> 16
        stn = (header_word >> 4) & 0x7FFF
    """
    # DIS PDU header (12 bytes)
    dis_header = bytearray(12)
    dis_header[2] = 26   # DIS_SIGNAL_PDU_TYPE

    # Signal PDU fields (20 bytes) — TDL type at offset 10 (big-endian)
    signal_fields = bytearray(20)
    struct.pack_into("!H", signal_fields, 10, 100)  # TDL_TYPE_LINK16

    # Link 16 Simulation Network Header (20 bytes)
    sim_header = bytearray(20)
    struct.pack_into("!H", sim_header, 0, npg)
    sim_header[5] = msg_type_id

    payload = bytes(dis_header) + bytes(signal_fields) + bytes(sim_header)

    # JTIDS header word (6 bytes) if msg_type_id == 0
    if msg_type_id == 0:
        # Production code reads 8 bytes big-endian at data_offset (with
        # 2 padding bytes appended), shifts right 16, then extracts
        # bits 4-18 as STN. We encode the inverse.
        raw_48 = (stn & 0x7FFF) << 4
        jtids = raw_48.to_bytes(6, byteorder="big")
        payload += jtids

    payload += b"".join(jwords)
    return payload


# ---------------------------------------------------------------------------
# Ethernet / IP / UDP frame builder
# ---------------------------------------------------------------------------

def make_udp_frame(
    payload: bytes,
    src_port: int = 4444,
    dst_port: int = 4444,
    src_ip: bytes = b"\xC0\xA8\x01\x01",   # 192.168.1.1
    dst_ip: bytes = b"\xC0\xA8\x01\x02",    # 192.168.1.2
) -> bytes:
    """Wrap a UDP payload in an Ethernet II / IPv4 / UDP frame.

    Produces a frame that ``reader.parse_frame()`` can strip.
    """
    # UDP header (8 bytes)
    udp_len = 8 + len(payload)
    udp_header = struct.pack("!HHHH", src_port, dst_port, udp_len, 0)

    # IPv4 header (20 bytes, no options)
    ip_total_len = 20 + udp_len
    ip_header = bytearray(20)
    ip_header[0] = 0x45          # version=4, IHL=5
    struct.pack_into("!H", ip_header, 2, ip_total_len)
    ip_header[8] = 64            # TTL
    ip_header[9] = 17            # protocol = UDP
    ip_header[12:16] = src_ip
    ip_header[16:20] = dst_ip

    # Ethernet II header (14 bytes)
    eth_header = b"\x00" * 6 + b"\x00" * 6 + struct.pack("!H", 0x0800)

    return eth_header + bytes(ip_header) + udp_header + payload


def make_tcp_frame(
    payload: bytes,
    src_port: int = 4444,
    dst_port: int = 4444,
    src_ip: bytes = b"\xC0\xA8\x01\x01",
    dst_ip: bytes = b"\xC0\xA8\x01\x02",
) -> bytes:
    """Wrap a TCP payload in an Ethernet II / IPv4 / TCP frame.

    Minimal TCP header (20 bytes, data offset = 5).
    """
    tcp_header = bytearray(20)
    struct.pack_into("!HH", tcp_header, 0, src_port, dst_port)
    tcp_header[12] = 0x50        # data offset = 5 (20 bytes), no flags

    ip_total_len = 20 + 20 + len(payload)
    ip_header = bytearray(20)
    ip_header[0] = 0x45
    struct.pack_into("!H", ip_header, 2, ip_total_len)
    ip_header[8] = 64
    ip_header[9] = 6             # protocol = TCP
    ip_header[12:16] = src_ip
    ip_header[16:20] = dst_ip

    eth_header = b"\x00" * 6 + b"\x00" * 6 + struct.pack("!H", 0x0800)

    return eth_header + bytes(ip_header) + bytes(tcp_header) + payload


# ---------------------------------------------------------------------------
# PCAP file builder
# ---------------------------------------------------------------------------

def make_pcap_file(frames: list[tuple[float, bytes]]) -> bytes:
    """Build a complete libpcap file from ``(timestamp, ethernet_frame)`` tuples.

    Uses magic ``0xA1B2C3D4`` (LE, microsecond resolution), version 2.4,
    snaplen 65535, link-layer type 1 (Ethernet).
    """
    global_header = struct.pack(
        "<IHHiIII",
        0xA1B2C3D4,   # magic
        2, 4,          # version
        0,             # timezone
        0,             # accuracy
        65535,         # snaplen
        1,             # linktype = Ethernet
    )

    records = bytearray()
    for ts, frame in frames:
        ts_sec = int(ts)
        ts_usec = int((ts - ts_sec) * 1_000_000)
        pkt_header = struct.pack("<IIII", ts_sec, ts_usec, len(frame), len(frame))
        records.extend(pkt_header)
        records.extend(frame)

    return global_header + bytes(records)


# ---------------------------------------------------------------------------
# Convenience composites
# ---------------------------------------------------------------------------

def make_simple_pcap(
    jwords_per_packet: list[list[bytes]],
    stn: int = 100,
    npg: int = 7,
    base_timestamp: float = 1_700_000_000.0,
) -> bytes:
    """Build a complete PCAP with SIMPLE-encapsulated Link 16 packets.

    Each inner list in *jwords_per_packet* becomes one PCAP packet.
    Timestamps increment by 1.0s per packet.
    """
    frames: list[tuple[float, bytes]] = []
    for i, jwords in enumerate(jwords_per_packet):
        simple_payload = make_simple_payload(jwords, stn=stn, npg=npg)
        frame = make_udp_frame(simple_payload)
        frames.append((base_timestamp + i, frame))
    return make_pcap_file(frames)


# ---------------------------------------------------------------------------
# pcapng file builder
# ---------------------------------------------------------------------------

def pad4(n: int) -> int:
    """Round *n* up to the next multiple of 4."""
    return (n + 3) & ~3


def make_pcapng_block(block_type: int, body: bytes, endian: str = "<") -> bytes:
    """Wrap *body* in a pcapng block envelope.

    Layout: BlockType(4) + BlockTotalLength(4) + body(padded) + BlockTotalLength(4).
    """
    padded_body = body + b"\x00" * (pad4(len(body)) - len(body))
    total_length = 4 + 4 + len(padded_body) + 4
    header = struct.pack(f"{endian}II", block_type, total_length)
    trailer = struct.pack(f"{endian}I", total_length)
    return header + padded_body + trailer


def make_pcapng_shb(endian: str = "<") -> bytes:
    """Build a Section Header Block (type 0x0A0D0D0A).

    Byte-Order Magic is written in *endian* order so readers can detect
    the file's byte order.
    """
    bom = struct.pack(f"{endian}I", 0x1A2B3C4D)
    version = struct.pack(f"{endian}HH", 1, 0)
    section_length = struct.pack(f"{endian}q", -1)  # unknown
    body = bom + version + section_length
    return make_pcapng_block(0x0A0D0D0A, body, endian)


def make_pcapng_idb(
    endian: str = "<",
    link_type: int = 1,
    snap_len: int = 0,
    ts_resolution: int | None = None,
) -> bytes:
    """Build an Interface Description Block (type 0x00000001).

    Args:
        link_type: Link-layer type (1 = Ethernet).
        snap_len: Maximum captured bytes per packet (0 = unlimited).
        ts_resolution: ``if_tsresol`` option byte, or ``None`` to omit
            (reader defaults to microsecond).
    """
    # IDB fixed fields: LinkType(2) + Reserved(2) + SnapLen(4)
    body = struct.pack(f"{endian}HHI", link_type, 0, snap_len)

    if ts_resolution is not None:
        # Option: type=9 (if_tsresol), length=1, value=1 byte, padded to 4
        opt = struct.pack(f"{endian}HH", 9, 1) + bytes([ts_resolution]) + b"\x00" * 3
        # End-of-options
        opt += struct.pack(f"{endian}HH", 0, 0)
        body += opt

    return make_pcapng_block(0x00000001, body, endian)


def make_pcapng_epb(
    timestamp: float,
    frame: bytes,
    interface_id: int = 0,
    ts_divisor: float = 1_000_000,
    endian: str = "<",
) -> bytes:
    """Build an Enhanced Packet Block (type 0x00000006).

    Converts *timestamp* (epoch seconds) to a 64-bit integer in units
    of the interface's timestamp resolution (*ts_divisor*).
    """
    raw_ts = int(timestamp * ts_divisor)
    ts_high = (raw_ts >> 32) & 0xFFFFFFFF
    ts_low = raw_ts & 0xFFFFFFFF
    captured_len = len(frame)
    original_len = len(frame)

    # EPB fixed fields: InterfaceID(4) + TsHigh(4) + TsLow(4) +
    #                    CapturedLen(4) + OriginalLen(4)
    header = struct.pack(
        f"{endian}IIIII",
        interface_id, ts_high, ts_low, captured_len, original_len,
    )
    # Packet data padded to 4-byte boundary (no options)
    padded_frame = frame + b"\x00" * (pad4(captured_len) - captured_len)

    body = header + padded_frame
    return make_pcapng_block(0x00000006, body, endian)


def make_pcapng_file(
    frames: list[tuple[float, bytes]],
    endian: str = "<",
    ts_resolution: int | None = None,
) -> bytes:
    """Build a complete pcapng file from ``(timestamp, ethernet_frame)`` tuples.

    Single-interface file with Ethernet link type. If *ts_resolution* is
    ``None``, the ``if_tsresol`` option is omitted (reader defaults to
    microsecond). Use ``6`` for explicit microseconds, ``9`` for nanoseconds.
    """
    ts_divisor = 1_000_000  # default microsecond
    if ts_resolution is not None:
        if ts_resolution & 0x80:
            ts_divisor = 2 ** (ts_resolution & 0x7F)
        else:
            ts_divisor = 10 ** (ts_resolution & 0x7F)

    parts = [
        make_pcapng_shb(endian),
        make_pcapng_idb(endian=endian, ts_resolution=ts_resolution),
    ]
    for ts, frame in frames:
        parts.append(make_pcapng_epb(ts, frame, ts_divisor=ts_divisor, endian=endian))

    return b"".join(parts)


def make_simple_pcapng(
    jwords_per_packet: list[list[bytes]],
    stn: int = 100,
    npg: int = 7,
    base_timestamp: float = 1_700_000_000.0,
) -> bytes:
    """Build a complete pcapng with SIMPLE-encapsulated Link 16 packets.

    Mirrors ``make_simple_pcap`` but produces pcapng output.
    """
    frames: list[tuple[float, bytes]] = []
    for i, jwords in enumerate(jwords_per_packet):
        simple_payload = make_simple_payload(jwords, stn=stn, npg=npg)
        frame = make_udp_frame(simple_payload)
        frames.append((base_timestamp + i, frame))
    return make_pcapng_file(frames)
