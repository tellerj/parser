"""Output formatters — render Track objects into human-readable reports.

Each formatter satisfies the ``OutputFormatter`` protocol defined in
``core/interfaces.py``.

How to add a new output format
===============================

1. Create a new module in this package (e.g. ``bullseye.py``).

2. Write a class with two members that match the ``OutputFormatter``
   protocol::

       from link16_parser.core.types import Track

       class BullseyeFormatter:
           @property
           def name(self) -> str:
               return "BULLSEYE"

           def format(self, track: Track) -> str:
               # Build a formatted string from the track's fields.
               # Handle None fields gracefully (substitute "UNK" etc.).
               # Return a copy/paste-ready string (no ANSI codes).
               ...

   No base class or inheritance needed — just match the method signatures.

3. Register it in ``__main__.py`` by adding it to the ``formatters`` dict::

       from link16_parser.output.bullseye import BullseyeFormatter
       formatters["BULLSEYE"] = BullseyeFormatter()

   The CLI shell will automatically pick it up — users can switch to
   it with the ``format BULLSEYE`` command.

4. Write a test in ``tests/`` that constructs a ``Track`` with known
   values and asserts the formatted output matches expectations.

Design notes
============

- Output must be **copy/paste ready** for direct dissemination.
  No ANSI escape codes, no trailing whitespace, no invisible characters.
- All formatters must handle ``None`` fields gracefully. Until the
  MIL-STD-6016 decoders are implemented, most fields will be ``None``.
- The ``coords`` module provides shared coordinate conversion utilities
  (decimal degrees -> military grid format) used by multiple formatters.

Existing implementations
========================

- ``tacrep.py``   — 5-line AIROP TACREP (formal military format).
- ``nineline.py`` — 9-line convenience format (informal).
- ``coords.py``   — Coordinate conversion utilities (not a formatter).
"""
