"""J-series message decoders — extract tactical data from raw J-words.

Each decoder handles exactly one (label, sublabel) pair and satisfies the
``MessageDecoder`` protocol defined in ``core/interfaces.py``.

How to add a new message type
=============================

Create a JSON definition file describing the bit-field layout. See
``schema.py`` for the format specification and ``scripts/validate_definitions.py``
to check your work.

The JSON file goes into the definitions directory — either the built-in
``link16/definitions/`` (for build-time integration) or a directory
passed via ``--definitions-dir`` / ``LINK16_DEFINITIONS`` env var.

Important: MIL-STD-6016 boundary
=================================

The J-word *envelope* (word format, label, sublabel, MLI — bits 0-12) is
publicly documented. Everything inside the 57-bit message-specific data
portion (bits 13-69) is defined in MIL-STD-6016 and is *not* public.

Message definitions describing bit layouts within the FWF data are CUI
and must be kept in a separate repository.

Existing implementations
========================

- ``definition_decoder.py`` — ``DefinitionDecoder``: JSON-driven decoder.
- ``loader.py``             — JSON definition loading + directory resolution.
- ``schema.py``             — JSON definition validation.
"""

from link16_parser.link16.messages.definition_decoder import DefinitionDecoder

__all__ = [
    "DefinitionDecoder",
]
