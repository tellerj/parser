"""Link 16 J-word parsing and message decoding.

Parses the public envelope of each J-word (word format, label, sublabel,
MLI) and routes complete messages to registered ``DefinitionDecoder``
implementations loaded from JSON definition files.

How to add a new message type
==============================

Create a JSON definition file describing the bit-field layout. See
``messages/schema.py`` for the format specification and
``scripts/validate_definitions.py`` to check your work.

Point the tool at the definitions directory via ``--definitions-dir``
or the ``LINK16_DEFINITIONS`` environment variable, or place the files
in the built-in ``definitions/`` directory at build time.

Existing implementations
========================

- ``parser.py``                    — ``JWordParser``: header parsing + decoder registry.
- ``messages/definition_decoder.py`` — ``DefinitionDecoder``: JSON-driven decoder.
- ``messages/loader.py``           — JSON definition loading + directory resolution.
- ``messages/schema.py``           — JSON definition validation.
"""

from __future__ import annotations

import logging

from link16_parser.link16.parser import JWordParser, parse_jword_header
from link16_parser.link16.messages.definition_decoder import DefinitionDecoder
from link16_parser.link16.messages.loader import (
    find_definitions_dir,
    load_definitions,
)

logger = logging.getLogger(__name__)


def build_parser(definitions_dir: str | None = None) -> JWordParser:
    """Create a ``JWordParser`` with decoders loaded from JSON definitions.

    Args:
        definitions_dir: Explicit path to a directory of JSON message
            definitions. If ``None``, searches ``LINK16_DEFINITIONS``
            env var and the built-in ``definitions/`` directory.

    Returns:
        A ``JWordParser`` ready to parse J-words from the encapsulation
        layer. If no definitions are found, the parser is returned with
        no decoders registered — unrecognised messages are silently skipped.
    """
    parser = JWordParser()

    defn_dir = find_definitions_dir(definitions_dir)
    if defn_dir is not None:
        try:
            decoders = load_definitions(defn_dir)
            for decoder in decoders:
                parser.register(decoder)
            if decoders:
                logger.info(
                    "Loaded %d definition decoder(s) from %s",
                    len(decoders), defn_dir,
                )
        except ValueError:
            logger.exception("Failed to load definitions from %s", defn_dir)
    else:
        logger.debug("No message definitions found — parser has no decoders")

    return parser


__all__ = [
    "build_parser",
    "JWordParser",
    "parse_jword_header",
    "DefinitionDecoder",
]
