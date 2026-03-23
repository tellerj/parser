"""Encapsulation decoders — strip transport-layer wrappers to extract J-words.

Each decoder handles one wire format (SIMPLE, DIS/SISO-J, JREAP-C, etc.)
and satisfies the ``EncapsulationDecoder`` protocol defined in
``core/interfaces.py``.

How to add a new encapsulation format
=====================================

1. Create a new module in this package (e.g. ``my_format.py``).

2. Write a class with two members that match the ``EncapsulationDecoder``
   protocol::

       class MyFormatDecoder:
           @property
           def name(self) -> str:
               return "MY-FORMAT"

           def decode(self, payload: bytes, pcap_timestamp: float) -> list[RawJWord]:
               # Validate magic bytes / header.
               # Parse your format's header to extract NPG, STN, word count.
               # Slice out each 10-byte J-word.
               # Return a list of RawJWord objects (or [] if invalid).
               ...

   No base class or inheritance needed — just match the method signatures.

3. Register it in two places:

   a. ``detect.py`` — add a heuristic check in ``AutoDecoder.decode()``
      (e.g. check for magic bytes) and add your decoder to the fallback
      list in ``__init__``.

   b. ``__main__.py`` — add your format to the ``build_encap_decoder()``
      lookup dict and to the ``--encap`` CLI choices.

4. Write a test in ``tests/`` that feeds known bytes through your decoder
   and asserts the correct ``RawJWord`` output.

Existing implementations
========================

- ``simple.py``  — STANAG 5602 / SIMPLE (fully documented, public).
- ``siso_j.py``  — DIS Signal PDU / SISO-STD-002 (fully documented, public).
- ``jreap_c.py`` — MIL-STD-3011 / JREAP-C (stub — awaiting spec access).
- ``detect.py``  — ``AutoDecoder`` heuristic dispatcher.
"""
