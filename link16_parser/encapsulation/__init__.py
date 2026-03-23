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

3. Register it in this file (``encapsulation/__init__.py``):

   a. Import your class.
   b. Add an entry to ``_DECODER_REGISTRY``.
   c. If your format has a heuristic signature (magic bytes, PDU type),
      add a fast-path check in ``detect.py:AutoDecoder.decode()``.

4. Write a test in ``tests/`` that feeds known bytes through your decoder
   and asserts the correct ``RawJWord`` output.

Existing implementations
========================

- ``simple.py``  — STANAG 5602 / SIMPLE (fully documented, public).
- ``siso_j.py``  — DIS Signal PDU / SISO-STD-002 (fully documented, public).
- ``jreap_c.py`` — MIL-STD-3011 / JREAP-C (stub — awaiting spec access).
- ``detect.py``  — ``AutoDecoder`` heuristic dispatcher.
"""

from __future__ import annotations

from link16_parser.core.interfaces import EncapsulationDecoder
from link16_parser.encapsulation.detect import AutoDecoder
from link16_parser.encapsulation.jreap_c import JreapCDecoder
from link16_parser.encapsulation.simple import SimpleDecoder
from link16_parser.encapsulation.siso_j import SisoJDecoder

# ---------------------------------------------------------------------------
# Decoder registry — maps CLI-friendly name to decoder class.
# To add a new format: import it above and add an entry here.
# ---------------------------------------------------------------------------

_DECODER_REGISTRY: dict[str, type[EncapsulationDecoder]] = {
    "simple": SimpleDecoder,
    "siso-j": SisoJDecoder,
    "jreap-c": JreapCDecoder,
}

ENCAP_CHOICES: list[str] = ["auto", *_DECODER_REGISTRY]


def build_decoder(name: str) -> EncapsulationDecoder:
    """Instantiate the encapsulation decoder for the given format name.

    Args:
        name: One of ``ENCAP_CHOICES`` — ``"auto"``, ``"simple"``,
              ``"siso-j"``, ``"jreap-c"``.

    Returns:
        An ``EncapsulationDecoder`` instance.

    Raises:
        KeyError: If *name* is not in ``ENCAP_CHOICES``.
    """
    if name == "auto":
        concrete = [cls() for cls in _DECODER_REGISTRY.values()]
        return AutoDecoder(decoders=concrete)
    return _DECODER_REGISTRY[name]()


__all__ = [
    "build_decoder",
    "ENCAP_CHOICES",
    "AutoDecoder",
    "SimpleDecoder",
    "SisoJDecoder",
    "JreapCDecoder",
]
