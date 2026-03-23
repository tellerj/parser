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
- **pcapng** (.pcapng) — detected and routed, but parsing is stubbed
  out. Gives a clear error with conversion instructions.

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
Register it in ``__main__.py`` alongside the existing source-selection
logic.

Existing implementations
========================

- ``reader.py`` — ``FileSource``: reads a capture file from disk
  (auto-detects libpcap vs pcapng).
- ``reader.py`` — ``PipeSource``: reads a live capture stream
  from stdin (``tcpdump -w -`` or similar).
- ``pcap_reader.py`` — libpcap format stream reader.
- ``pcapng_reader.py`` — pcapng format stream reader (stub, awaiting
  implementation).
"""
