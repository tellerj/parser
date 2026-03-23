"""Link 16 J-word parsing and message decoding.

Parses the public envelope of each J-word (word format, label, sublabel,
MLI) and routes complete messages to registered ``MessageDecoder``
implementations.

How to add a new message decoder
=================================

1. Create a new module in ``link16/messages/`` (e.g. ``j7_0.py``).

2. Write a class that matches the ``MessageDecoder`` protocol — see the
   detailed guide in ``link16/messages/__init__.py``.

3. Register it in this file (``link16/__init__.py``) inside
   ``build_parser()``::

       from link16_parser.link16.messages.j7_0 import J70DataUpdateDecoder
       parser.register(J70DataUpdateDecoder())

4. Write a test in ``tests/`` that constructs known J-words and asserts
   the correct ``Link16Message`` output.

Existing implementations
========================

- ``parser.py``       — ``JWordParser``: header parsing + decoder registry.
- ``messages/j2_2.py``  — J2.2 Air PPLI (stub — awaiting MIL-STD-6016).
- ``messages/j3_2.py``  — J3.2 Air Track (stub — awaiting MIL-STD-6016).
- ``messages/j28_2.py`` — J28.2 Free Text (stub — awaiting MIL-STD-6016).
"""

from __future__ import annotations

from link16_parser.link16.parser import JWordParser, parse_jword_header
from link16_parser.link16.messages.j2_2 import J22AirPpliDecoder
from link16_parser.link16.messages.j3_2 import J32AirTrackDecoder
from link16_parser.link16.messages.j28_2 import J282FreeTextDecoder


def build_parser() -> JWordParser:
    """Create a ``JWordParser`` with all available message decoders registered.

    Returns:
        A ``JWordParser`` ready to parse J-words from the encapsulation layer.
    """
    parser = JWordParser()
    parser.register(J22AirPpliDecoder())
    parser.register(J32AirTrackDecoder())
    parser.register(J282FreeTextDecoder())
    return parser


__all__ = [
    "build_parser",
    "JWordParser",
    "parse_jword_header",
    "J22AirPpliDecoder",
    "J32AirTrackDecoder",
    "J282FreeTextDecoder",
]
