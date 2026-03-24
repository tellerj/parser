"""Output formatters — render Track objects into human-readable reports.

Each formatter satisfies the ``OutputFormatter`` protocol defined in
``core/interfaces.py``.

How to add a new output format
===============================

1. Create a new module in this package (e.g. ``kml_format.py``).

2. Write a class with two members that match the ``OutputFormatter``
   protocol::

       from link16_parser.core.types import Track

       class KmlFormatter:
           @property
           def name(self) -> str:
               return "KML"

           def format(self, track: Track) -> str:
               # Build a formatted string from the track's fields.
               # Handle None fields gracefully (substitute "UNK" etc.).
               # Return a copy/paste-ready string (no ANSI codes).
               ...

   No base class or inheritance needed — just match the method signatures.

3. Register it in this file (``output/__init__.py``) inside
   ``build_formatters()``::

       from link16_parser.output.kml_format import KmlFormatter
       formatters["KML"] = KmlFormatter()

   The CLI shell will automatically pick it up — users can switch to
   it with the ``format KML`` command.

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

- ``tacrep_format.py``   — 5-line AIROP TACREP (formal military format).
- ``nineline_format.py`` — 9-line convenience format (informal).
- ``json_format.py``     — NDJSON (machine-readable, structured).
- ``csv_format.py``      — CSV (machine-readable, flat columns).
- ``bullseye_format.py`` — Bullseye (bearing/distance from reference point).
- ``coords.py``          — Coordinate conversion utilities (not a formatter).
"""

from __future__ import annotations

from link16_parser.core.interfaces import OutputFormatter
from link16_parser.output.bullseye_format import BullseyeFormatter
from link16_parser.output.csv_format import CsvFormatter
from link16_parser.output.json_format import JsonFormatter
from link16_parser.output.nineline_format import NineLineFormatter
from link16_parser.output.tacrep_format import TacrepFormatter


def build_formatters(
    originator: str = "L16-PARSER",
    classification: str = "UNCLAS",
    bullseye_lat: float | None = None,
    bullseye_lon: float | None = None,
) -> dict[str, OutputFormatter]:
    """Create the standard set of output formatters.

    Args:
        originator: The TACREP originator field (e.g. ``"CTF124"``).
        classification: Classification marking (e.g. ``"SECRET"``).
        bullseye_lat: Bullseye reference latitude. Required for BULLSEYE format.
        bullseye_lon: Bullseye reference longitude. Required for BULLSEYE format.

    Returns:
        A dict mapping format name to ``OutputFormatter`` instance.
        Keys match the names used by the CLI ``format`` command.
    """
    formatters: dict[str, OutputFormatter] = {
        "TACREP": TacrepFormatter(
            originator=originator,
            classification=classification,
        ),
        "9-LINE": NineLineFormatter(),
        "JSON": JsonFormatter(),
        "CSV": CsvFormatter(),
    }
    if bullseye_lat is not None and bullseye_lon is not None:
        formatters["BULLSEYE"] = BullseyeFormatter(
            bull_lat=bullseye_lat, bull_lon=bullseye_lon,
        )
    return formatters


__all__ = [
    "build_formatters",
    "TacrepFormatter",
    "NineLineFormatter",
    "JsonFormatter",
    "CsvFormatter",
    "BullseyeFormatter",
]
