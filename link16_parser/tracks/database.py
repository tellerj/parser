"""In-memory track database.

Maintains the most recent state for each tracked entity, keyed by STN.
Supports lookup by STN, track number, or callsign. Notifies registered
listeners on every track update, enabling downstream consumers (network
output, visualizers) to react in near-real-time.

Thread-safe for single-writer / multiple-reader use (ingestion thread
writes, CLI thread and network output threads read).
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Iterator

from link16_parser.core.types import Link16Message, Track

logger = logging.getLogger(__name__)

# Type alias for update listener callbacks
TrackListener = Callable[[Track, Link16Message], None]


class TrackDatabase:
    """In-memory store of ``Track`` objects, keyed by Source Track Number.

    Thread safety: all public methods acquire a lock, making this safe
    for the single-writer (ingestion thread) / multiple-reader (CLI thread,
    network output threads) pattern used by the main entry point.

    Supports an observer pattern: registered listeners are called after
    every track update, inside the lock. Listeners should be fast and
    non-blocking — heavy work (network I/O, formatting) should be
    dispatched to a queue or separate thread.
    """

    def __init__(self) -> None:
        self._tracks: dict[int, Track] = {}  # keyed by STN
        self._lock = threading.Lock()
        self._listeners: list[TrackListener] = []

    def on_update(self, listener: TrackListener) -> None:
        """Register a callback invoked after every track update.

        The callback receives the updated ``Track`` and the
        ``Link16Message`` that triggered the update. It is called
        inside the database lock — keep it fast and non-blocking.

        Args:
            listener: A callable ``(Track, Link16Message) -> None``.
        """
        self._listeners.append(listener)

    def update(self, message: Link16Message) -> Track:
        """Update (or create) a track from a decoded Link 16 message.

        Performs a non-destructive merge: only fields that are non-None
        in the message overwrite the track's current value. This means
        a J2.2 PPLI (which carries position but not identity) won't
        clobber the identity set by an earlier J3.2 Air Track.

        After merging, all registered listeners are notified.

        Args:
            message: A decoded ``Link16Message``. Its ``stn`` field
                determines which track to update (or create).

        Returns:
            The updated (or newly created) ``Track`` object.
        """
        with self._lock:
            track = self._tracks.get(message.stn)
            if track is None:
                track = Track(stn=message.stn)
                self._tracks[message.stn] = track

            # Merge fields — only update if the message carries a value
            if message.position is not None:
                track.position = message.position
            if message.identity is not None:
                track.identity = message.identity
            if message.platform is not None:
                track.platform = message.platform
            if message.callsign is not None:
                track.callsign = message.callsign
            if message.heading_deg is not None:
                track.heading_deg = message.heading_deg
            if message.speed_kph is not None:
                track.speed_kph = message.speed_kph

            # Track number from message fields if provided
            tn = message.fields.get("track_number")
            if isinstance(tn, str):
                track.track_number = tn

            track.last_updated = message.timestamp
            track.message_count += 1

            # Notify listeners
            for listener in self._listeners:
                try:
                    listener(track, message)
                except Exception:
                    listener_name = getattr(listener, "__qualname__", repr(listener))
                    logger.exception(
                        "Track update listener '%s' failed while processing "
                        "STN %d (%s message)",
                        listener_name, track.stn, message.msg_type,
                    )

            return track

    def get_by_stn(self, stn: int) -> Track | None:
        """Look up a track by Source Track Number.

        Args:
            stn: The integer STN to search for (exact match).

        Returns:
            The matching ``Track``, or ``None`` if not found.
        """
        with self._lock:
            return self._tracks.get(stn)

    def get_by_callsign(self, callsign: str) -> Track | None:
        """Look up a track by callsign (case-insensitive).

        Args:
            callsign: The callsign string to match (e.g. ``"RULDOG01"``).

        Returns:
            The first matching ``Track``, or ``None``. If multiple tracks
            share a callsign (shouldn't happen), returns the first found.
        """
        callsign_upper = callsign.upper()
        with self._lock:
            for track in self._tracks.values():
                if track.callsign and track.callsign.upper() == callsign_upper:
                    return track
        return None

    def get_by_track_number(self, track_number: str) -> Track | None:
        """Look up a track by its 5-character alphanumeric track number.

        Args:
            track_number: The track number string (exact match).

        Returns:
            The matching ``Track``, or ``None``.
        """
        with self._lock:
            for track in self._tracks.values():
                if track.track_number == track_number:
                    return track
        return None

    def find(self, query: str) -> Track | None:
        """Look up a track by any identifier — the CLI's universal search.

        Resolution order:
            1. Try as STN (integer, or 5-digit octal).
            2. Try as track number (exact string match).
            3. Try as callsign (case-insensitive).

        Args:
            query: A user-supplied identifier string.

        Returns:
            The first matching ``Track``, or ``None``.
        """
        # Try as STN (integer)
        try:
            stn = int(query, 8) if len(query) == 5 else int(query)
            result = self.get_by_stn(stn)
            if result is not None:
                return result
        except ValueError:
            pass

        # Try as track number
        result = self.get_by_track_number(query)
        if result is not None:
            return result

        # Try as callsign
        return self.get_by_callsign(query)

    def all_tracks(self) -> list[Track]:
        """Return a snapshot of all current tracks, sorted by last update."""
        with self._lock:
            tracks = list(self._tracks.values())
        tracks.sort(key=lambda t: t.last_updated or t.stn, reverse=True)
        return tracks

    def __len__(self) -> int:
        with self._lock:
            return len(self._tracks)

    def __iter__(self) -> Iterator[Track]:
        return iter(self.all_tracks())
