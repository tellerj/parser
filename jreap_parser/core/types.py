"""Core data types shared across all modules.

These dataclasses are the 'currency' that flows between layers::

    PacketSource -> EncapsulationDecoder -> JWordParser -> TrackDatabase -> OutputFormatter

Each layer consumes one type and produces the next:

- ``PacketSource`` yields raw packet bytes.
- ``EncapsulationDecoder`` consumes bytes, produces ``RawJWord``.
- ``JWordParser`` + ``MessageDecoder`` consume ``RawJWord``, produce ``Link16Message``.
- ``TrackDatabase`` consumes ``Link16Message``, maintains ``Track`` state.
- ``OutputFormatter`` consumes ``Track``, produces formatted strings.

Docstring convention: Google style throughout this project.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class Identity(Enum):
    """Track identity classification (from J3.x surveillance messages)."""

    PENDING = "PENDING"
    UNKNOWN = "UNKNOWN"
    ASSUMED_FRIEND = "ASSUMED FRIEND"
    FRIEND = "FRIEND"
    NEUTRAL = "NEUTRAL"
    SUSPECT = "SUSPECT"
    HOSTILE = "HOSTILE"


class WordFormat(IntEnum):
    """J-word format type (bits 0-1 of each 75-bit word)."""

    INITIAL = 0
    CONTINUATION = 1
    EXTENSION = 2


# ---------------------------------------------------------------------------
# Position
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Position:
    """Geographic position in decimal degrees.

    Attributes:
        lat: Latitude in decimal degrees. Positive = North, negative = South.
        lon: Longitude in decimal degrees. Positive = East, negative = West.
        alt_m: Altitude in meters above sea level, or None if unavailable.
    """

    lat: float
    lon: float
    alt_m: float | None = None


# ---------------------------------------------------------------------------
# Platform identification
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlatformId:
    """Aircraft / platform identification extracted from Link 16 messages.

    Attributes:
        generic_type: Platform category code — e.g. ``"FTR"`` (fighter),
            ``"BMR"`` (bomber), ``"ATK"`` (attack), ``"TTY"`` (transport).
            Sourced from J2.2 PPLI or J3.2 Air Track messages.
        specific_type: Aircraft designation — e.g. ``"F16C"``, ``"F15E"``,
            ``"F22"``. Only available from J3.2 Air Track (not J2.2 PPLI).
        nationality: Two-letter country code — e.g. ``"US"``, ``"UK"``.
    """

    generic_type: str | None = None
    specific_type: str | None = None
    nationality: str | None = None


# ---------------------------------------------------------------------------
# Raw J-word (output of encapsulation decoder)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RawJWord:
    """A single 80-bit J-series word with metadata from the encapsulation layer.

    This is what an ``EncapsulationDecoder`` produces and what the
    ``JWordParser`` consumes. Each word is 75 useful bits (70 data +
    5 parity) padded to 80 bits (10 bytes) for byte alignment.

    Attributes:
        data: The raw word bytes — exactly 10 bytes (80 bits).
            Layout: 70 bits FWF data + 5 bits parity + 5 bits padding.
        stn: Source Track Number identifying the transmitting JU.
            Extracted from the Link 16 Header Word or encapsulation header.
        npg: Network Participation Group number (0-511). Indicates the
            information category (e.g. 5/6 = PPLI, 7 = Surveillance).
        timestamp: Best-available UTC timestamp for this word, derived
            from the encapsulation layer or the PCAP frame header.
    """

    data: bytes
    stn: int
    npg: int
    timestamp: datetime


# ---------------------------------------------------------------------------
# Parsed Link 16 message (output of message decoders)
# ---------------------------------------------------------------------------

@dataclass
class Link16Message:
    """A decoded Link 16 message.

    Produced by a ``MessageDecoder`` from one or more ``RawJWord`` objects.
    Common tactical fields are promoted to top-level attributes so that
    downstream consumers (``TrackDatabase``, formatters) don't need to
    know which message type they came from. The ``fields`` dict carries
    anything message-type-specific that doesn't fit the common schema.

    Attributes:
        msg_type: Message type identifier — e.g. ``"J2.2"``, ``"J3.2"``,
            ``"J28.2"``. Matches the ``MessageDecoder.msg_type_name`` prefix.
        stn: Source Track Number of the transmitting JU.
        timestamp: UTC timestamp of this message.
        position: Geographic position, or None if not carried / not yet decoded.
        identity: Friend/hostile/neutral classification, or None.
        platform: Aircraft type and nationality, or None.
        callsign: Voice callsign string, or None.
        heading_deg: Course/heading in degrees (0-360), or None.
        speed_kph: Speed in kilometers per hour, or None.
        fields: Message-type-specific data that doesn't fit the common
            attributes. Keys and value types vary by ``msg_type``.
    """

    msg_type: str
    stn: int
    timestamp: datetime
    position: Position | None = None
    identity: Identity | None = None
    platform: PlatformId | None = None
    callsign: str | None = None
    heading_deg: float | None = None
    speed_kph: float | None = None
    fields: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Track (maintained by TrackDatabase)
# ---------------------------------------------------------------------------

@dataclass
class Track:
    """Aggregated state for a single tracked entity (aircraft, ship, etc.).

    ``TrackDatabase`` owns these objects and updates them incrementally as
    new ``Link16Message`` objects arrive. The CLI shell and output formatters
    read them but never modify them directly.

    Each field represents the *most recent known value* — when a new message
    carries a non-None value for a field, it overwrites the previous one.
    Fields that a message doesn't carry are left unchanged.

    Attributes:
        stn: Source Track Number — the primary key in ``TrackDatabase``.
        track_number: 5-character alphanumeric track number (e.g. ``"A1234"``),
            if known from J3.x surveillance messages.
        callsign: Voice callsign (e.g. ``"RULDOG01"``), if known.
        position: Last-known geographic position.
        identity: Last-known friend/hostile/neutral classification.
        platform: Last-known aircraft type and nationality.
        heading_deg: Last-known course/heading in degrees (0-360).
        speed_kph: Last-known speed in kilometers per hour.
        last_updated: UTC timestamp of the most recent message for this track.
        message_count: Total number of Link 16 messages received for this track.
    """

    stn: int
    track_number: str | None = None
    callsign: str | None = None
    position: Position | None = None
    identity: Identity | None = None
    platform: PlatformId | None = None
    heading_deg: float | None = None
    speed_kph: float | None = None
    last_updated: datetime | None = None
    message_count: int = 0
