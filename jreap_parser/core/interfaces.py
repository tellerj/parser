"""Protocol (interface) definitions for pluggable components.

Each ``Protocol`` class below defines the contract that a pluggable module
must satisfy. The actual implementations live in their respective packages:

- ``EncapsulationDecoder`` -> ``encapsulation/``
- ``MessageDecoder`` -> ``link16/messages/``
- ``OutputFormatter`` -> ``output/``
- ``PacketSource`` -> ``ingestion/``

To add a new implementation, write a class that matches the protocol's
method signatures and register it with the appropriate wiring code in
``__main__.py``. No base-class inheritance is required — Python's structural
subtyping (duck typing) handles the rest.

Docstring convention: Google style throughout this project.
"""

from __future__ import annotations

from typing import Iterator, Protocol

from jreap_parser.core.types import Link16Message, RawJWord, Track


# ---------------------------------------------------------------------------
# Packet ingestion
# ---------------------------------------------------------------------------

class PacketSource(Protocol):
    """Yields raw UDP/TCP payloads extracted from a PCAP source.

    Implementations handle the difference between reading a file on disk
    vs. reading a live byte stream from stdin. Everything downstream of
    this interface is source-agnostic.

    Implementations:
        ``PcapFileSource`` — reads a ``.pcap`` file from disk.
        ``PcapPipeSource`` — reads a live PCAP stream from stdin.
    """

    def packets(self) -> Iterator[tuple[float, bytes]]:
        """Yield packets as ``(pcap_timestamp, raw_payload)`` tuples.

        Yields:
            A tuple of:
            - **pcap_timestamp** (``float``): Epoch seconds from the PCAP
              frame header (seconds + microseconds).
            - **raw_payload** (``bytes``): The UDP or TCP payload bytes
              *after* Ethernet and IP headers have been stripped.

        The iterator terminates when the source is exhausted (EOF for
        files, broken pipe / Ctrl-C for live streams).
        """
        ...


# ---------------------------------------------------------------------------
# Encapsulation decoding
# ---------------------------------------------------------------------------

class EncapsulationDecoder(Protocol):
    """Strips a transport-layer encapsulation and extracts raw J-words.

    A packet captured off the wire contains Link 16 J-words wrapped in
    a protocol-specific envelope (SIMPLE, DIS/SISO-J, JREAP-C, etc.).
    Each ``EncapsulationDecoder`` knows how to unwrap one format and
    produce ``RawJWord`` objects that the ``JWordParser`` can consume.

    Implementations:
        ``SimpleDecoder`` — STANAG 5602 (fully documented, public).
        ``SisoJDecoder``  — DIS Signal PDU / SISO-STD-002 (public).
        ``JreapCDecoder``  — MIL-STD-3011 (stub, awaiting spec).
        ``AutoDecoder``   — heuristic dispatcher that tries all of the above.
    """

    @property
    def name(self) -> str:
        """Human-readable name for this encapsulation format.

        Returns:
            Short identifier string — e.g. ``"SIMPLE"``, ``"SISO-J"``.
        """
        ...

    def decode(self, payload: bytes, pcap_timestamp: float) -> list[RawJWord]:
        """Decode a single packet payload into zero or more J-words.

        Args:
            payload: Raw UDP/TCP payload bytes. IP headers have already
                been stripped by the ``PacketSource``.
            pcap_timestamp: Epoch-seconds timestamp from the PCAP frame
                header. Used as the timestamp on extracted ``RawJWord``
                objects when the encapsulation format doesn't carry its
                own timing information.

        Returns:
            List of ``RawJWord`` objects extracted from this packet.
            Returns an empty list if the payload is not valid for this
            encapsulation format (wrong magic bytes, too short, etc.).
            This is not an error — the ``AutoDecoder`` relies on this
            behavior to try multiple formats.
        """
        ...


# ---------------------------------------------------------------------------
# Link 16 message decoding
# ---------------------------------------------------------------------------

class MessageDecoder(Protocol):
    """Decodes a specific J-series message type from raw J-words.

    Each implementation handles exactly one ``(label, sublabel)`` pair —
    e.g. ``(2, 2)`` for J2.2 Air PPLI. Implementations are registered
    with ``JWordParser.register()`` and dispatched automatically when
    the parser encounters a matching initial word.

    Implementations:
        ``J22AirPpliDecoder``  — J2.2 Air PPLI (stub, awaiting MIL-STD-6016).
        ``J32AirTrackDecoder`` — J3.2 Air Track (stub, awaiting MIL-STD-6016).
        ``J282FreeTextDecoder`` — J28.2 Free Text (stub, awaiting MIL-STD-6016).
    """

    @property
    def label(self) -> int:
        """J-word label value (bits 2-6 of the initial word), range 0-31.

        Returns:
            The label this decoder is responsible for.
        """
        ...

    @property
    def sublabel(self) -> int:
        """J-word sublabel value (bits 7-9 of the initial word), range 0-7.

        Returns:
            The sublabel this decoder is responsible for.
        """
        ...

    @property
    def msg_type_name(self) -> str:
        """Human-readable message type name.

        Returns:
            A string like ``"J2.2 Air PPLI"`` or ``"J3.2 Air Track"``.
            Used in logging and debug output.
        """
        ...

    def decode(self, words: list[RawJWord]) -> Link16Message | None:
        """Decode a complete message from its constituent J-words.

        The ``JWordParser`` groups words into messages using the MLI
        (Message Length Indicator) from the initial word header, then
        passes the full group to this method.

        Args:
            words: The initial word followed by any extension and
                continuation words that belong to this message. The list
                always contains at least one word (the initial word).
                Word order matches the order in the packet.

        Returns:
            A ``Link16Message`` with whatever fields could be extracted,
            or ``None`` if the message is malformed or cannot be decoded.
            Returning ``None`` causes the parser to silently skip the
            message (not an error).
        """
        ...


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

class OutputFormatter(Protocol):
    """Formats a ``Track`` into a human-readable report string.

    Output must be copy/paste ready for dissemination: no ANSI escape
    codes, no trailing whitespace, no invisible characters.

    Implementations:
        ``TacrepFormatter``   — 5-line AIROP TACREP (formal military format).
        ``NineLineFormatter`` — 9-line convenience format (informal).
    """

    @property
    def name(self) -> str:
        """Format name used in CLI commands and the ``format`` switcher.

        Returns:
            An uppercase identifier — e.g. ``"TACREP"``, ``"9-LINE"``.
        """
        ...

    def format(self, track: Track) -> str:
        """Produce a formatted report string for the given track.

        Args:
            track: The track to format. Fields may be ``None`` if the
                data hasn't been decoded yet (e.g. before MIL-STD-6016
                decoders are implemented). Formatters must handle ``None``
                gracefully, substituting ``"UNK"`` or equivalent.

        Returns:
            A multi-line string ready to copy/paste for dissemination.
            No ANSI codes, no trailing whitespace.
        """
        ...
