"""J-word header parser and message decoder registry.

Parses the public envelope of each J-word (word format, label, sublabel, MLI)
and routes complete messages to registered MessageDecoder implementations.
"""

from __future__ import annotations

import logging
import struct
from typing import Callable

from link16_parser.core.interfaces import MessageDecoder
from link16_parser.core.types import Link16Message, RawJWord, WordFormat

logger = logging.getLogger(__name__)

# Bit masks for the first 16 bits of a J-word (little-endian)
MASK_WORD_FORMAT = 0x0003   # bits 0-1
MASK_LABEL = 0x007C         # bits 2-6
MASK_SUBLABEL = 0x0380      # bits 7-9
MASK_MLI = 0x1C00           # bits 10-12

SHIFT_LABEL = 2
SHIFT_SUBLABEL = 7
SHIFT_MLI = 10


def parse_jword_header(word: RawJWord) -> tuple[WordFormat, int, int, int]:
    """Extract the envelope header fields from a J-word.

    Reads the first two bytes (little-endian) and masks out the four
    header fields that are publicly documented. Everything beyond these
    13 bits (the 57-bit message-specific data) requires MIL-STD-6016.

    Args:
        word: A single ``RawJWord`` (must have at least 2 bytes of data).

    Returns:
        A 4-tuple of ``(word_format, label, sublabel, mli)`` where:

        - **word_format**: ``WordFormat`` enum (INITIAL / CONTINUATION / EXTENSION).
        - **label**: Message category, 0-31 (bits 2-6).
        - **sublabel**: Message sub-type, 0-7 (bits 7-9).
        - **mli**: Message Length Indicator, 0-7 (bits 10-12).
          Indicates how many *additional* words follow the initial word.
    """
    cache = struct.unpack_from("<H", word.data, 0)[0]

    word_format = WordFormat(cache & MASK_WORD_FORMAT)
    label = (cache & MASK_LABEL) >> SHIFT_LABEL
    sublabel = (cache & MASK_SUBLABEL) >> SHIFT_SUBLABEL
    mli = (cache & MASK_MLI) >> SHIFT_MLI

    return word_format, label, sublabel, mli


class JWordParser:
    """Parses J-word envelopes and dispatches to registered message decoders.

    Usage:
        parser = JWordParser()
        parser.register(my_j22_decoder)
        parser.register(my_j32_decoder)

        for message in parser.parse(raw_words):
            track_db.update(message)
    """

    def __init__(self) -> None:
        self._decoders: dict[tuple[int, int], MessageDecoder] = {}
        self._on_unknown: Callable[[int, int, list[RawJWord]], None] | None = None

    def register(self, decoder: MessageDecoder) -> None:
        """Register a message decoder for a ``(label, sublabel)`` pair.

        Args:
            decoder: A ``MessageDecoder`` implementation. Its ``label`` and
                ``sublabel`` properties determine the routing key. If a
                decoder is already registered for that key, it is replaced.
        """
        key = (decoder.label, decoder.sublabel)
        self._decoders[key] = decoder
        logger.debug("Registered decoder for J%d.%d: %s", *key, decoder.msg_type_name)

    def on_unknown(self, callback: Callable[[int, int, list[RawJWord]], None]) -> None:
        """Set a callback invoked when no decoder is registered for a message.

        Args:
            callback: Called with ``(label, sublabel, words)`` for each
                unhandled message. Useful for logging or statistics.
        """
        self._on_unknown = callback

    def parse(self, words: list[RawJWord]) -> list[Link16Message]:
        """Parse a sequence of J-words into decoded Link 16 messages.

        Walks the word list linearly. For each initial word, reads the
        MLI to determine how many words belong to the message, slices
        them off, looks up the ``(label, sublabel)`` decoder, and
        delegates. Orphaned continuation/extension words are skipped.

        Args:
            words: A flat list of ``RawJWord`` objects from a single
                packet, in the order they appeared in the payload.

        Returns:
            List of successfully decoded ``Link16Message`` objects.
            Messages with no registered decoder or that return ``None``
            from the decoder are silently omitted.
        """
        messages: list[Link16Message] = []
        i = 0

        while i < len(words):
            word = words[i]
            wf, label, sublabel, mli = parse_jword_header(word)

            if wf != WordFormat.INITIAL:
                # Orphaned continuation/extension word — skip
                i += 1
                continue

            # MLI tells us how many total words in this message
            # (including the initial word). 0 means 1 word.
            msg_word_count = mli + 1 if mli > 0 else 1
            msg_words = words[i : i + msg_word_count]
            i += msg_word_count

            # Look up decoder
            key = (label, sublabel)
            decoder = self._decoders.get(key)

            if decoder is None:
                if self._on_unknown is not None:
                    self._on_unknown(label, sublabel, msg_words)
                continue

            result = decoder.decode(msg_words)
            if result is not None:
                messages.append(result)

        return messages
