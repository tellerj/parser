"""Packet ingestion — read capture data from files or live streams.

Each source satisfies the ``PacketSource`` protocol defined in
``core/interfaces.py``. Sources yield ``(timestamp, payload)`` tuples
where *timestamp* is epoch-seconds (``float``) and *payload* is the
raw transport-layer bytes after Ethernet/IP headers have been stripped.

The ``float`` timestamp is intentional at this layer — it's the raw
capture value with no interpretation. The encapsulation decoders
downstream convert it to ``datetime`` when constructing ``RawJWord``
objects.

Format auto-detection
=====================

``FileSource`` and ``PipeSource`` auto-detect the capture format from
the stream's leading magic bytes, the same way the encapsulation
component's ``AutoDecoder`` identifies packet formats. Currently
supported:

- **libpcap** (.pcap) — fully implemented.
- **pcapng** (.pcapng) — fully supported.

To add a new capture format, implement a ``read_<format>_stream()``
generator in a new module, then add its magic bytes to the detection
logic in ``reader._auto_detect_stream()``.

How to add a new packet source
==============================

If you need a fundamentally different input mechanism (not a file or
pipe — e.g. a network socket, a message queue, or an API), create a
new class that satisfies the ``PacketSource`` protocol::

    from typing import Iterator

    class MyCustomSource:
        def packets(self) -> Iterator[tuple[float, bytes]]:
            # Yield (epoch_seconds, transport_payload) tuples.
            ...

No base class or inheritance needed — just match the method signature.
Register it in this file (``ingestion/__init__.py``) inside
``build_source()``.

Existing implementations
========================

- ``reader.py`` — ``FileSource``: reads a capture file from disk
  (auto-detects libpcap vs pcapng).
- ``reader.py`` — ``PipeSource``: reads a live capture stream
  from stdin (``tcpdump -w -`` or similar).
- ``pcap_reader.py`` — libpcap format stream reader.
- ``pcapng_reader.py`` — pcapng format stream reader.
"""

from __future__ import annotations

from link16_parser.core.interfaces import PacketSource
from link16_parser.ingestion.reader import FileSource, PipeSource


def build_source(
    file: str | None = None,
    pipe: bool = False,
    port_filter: int | None = None,
) -> PacketSource:
    """Instantiate the appropriate packet source.

    Args:
        file: Path to a capture file on disk. Mutually exclusive with *pipe*.
        pipe: If ``True``, read a live capture stream from stdin.
        port_filter: If set, only yield packets where either the source
            or destination port matches this value.

    Returns:
        A ``PacketSource`` instance (``FileSource`` or ``PipeSource``).

    Raises:
        ValueError: If neither *file* nor *pipe* is specified.
    """
    if file:
        return FileSource(file, port_filter=port_filter)
    if pipe:
        return PipeSource(port_filter=port_filter)
    raise ValueError("Either 'file' or 'pipe' must be specified")


__all__ = [
    "build_source",
    "FileSource",
    "PipeSource",
]
