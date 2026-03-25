"""Network output sinks — stream track data to remote endpoints.

Each sink satisfies the ``OutputSink`` protocol defined in
``core/interfaces.py``. Sinks are push-based: they react to every
track update via the ``TrackDatabase.on_update()`` callback and
deliver formatted data to a downstream consumer over the network.

How to add a new network sink
==============================

1. Create a new module in this package (e.g. ``multicast.py``).

2. Write a class with four members that match the ``OutputSink``
   protocol::

       import socket
       from link16_parser.core.types import Track, Link16Message

       class MulticastSink:
           @property
           def name(self) -> str:
               return "MCAST:239.1.1.1:5000"

           def start(self) -> None:
               # Open the multicast socket, join group, etc.
               ...

           def stop(self) -> None:
               # Close the socket. Must be idempotent.
               ...

           def on_track_update(self, track: Track, message: Link16Message | None) -> None:
               # Format and send. Called inside the DB lock — be fast.
               # For heavy work, enqueue and return immediately.
               ...

   No base class or inheritance needed — just match the method signatures.

3. Register it in ``__main__.py``::

       from link16_parser.network import MulticastSink
       sink = MulticastSink(...)
       sink.start()
       track_db.on_update(sink.on_track_update)
       # ... and sink.stop() in the finally block.

Design notes
============

- ``on_track_update()`` is called inside the ``TrackDatabase`` lock.
  Blocking I/O in that callback stalls the ingestion thread. For
  network sinks, the recommended pattern is to enqueue the data in
  a ``queue.Queue`` and have a separate sender thread drain it.
  ``NetworkSink`` implements this pattern.

- Sinks receive every update for every track. If you only care about
  specific tracks or message types, filter inside ``on_track_update()``.

Existing implementations
========================

- ``sink.py`` — ``NetworkSink``: streams formatted reports over TCP or UDP.
"""

from link16_parser.network.sink import NetworkSink

__all__ = ["NetworkSink"]
