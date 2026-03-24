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
from dataclasses import replace
from typing import Iterator

from link16_parser.core.interfaces import TrackListener
from link16_parser.core.types import Link16Message, PlatformId, Position, Track

logger = logging.getLogger(__name__)


def _snapshot(track: Track) -> Track:
    """Create a deep-enough copy of a Track for snapshot isolation.

    ``dataclasses.replace()`` is shallow — mutable containers like
    ``fields`` would alias the live track's dict. This helper copies
    the ``fields`` dict so snapshots are fully independent.
    """
    return replace(track, fields=dict(track.fields))


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
        with self._lock:
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
                if track.position is not None:
                    track.position = Position(
                        lat=message.position.lat,
                        lon=message.position.lon,
                        alt_m=message.position.alt_m if message.position.alt_m is not None else track.position.alt_m,
                    )
                else:
                    track.position = message.position
            if message.identity is not None:
                track.identity = message.identity
            if message.platform is not None:
                if track.platform is not None:
                    track.platform = PlatformId(
                        generic_type=message.platform.generic_type if message.platform.generic_type is not None else track.platform.generic_type,
                        specific_type=message.platform.specific_type if message.platform.specific_type is not None else track.platform.specific_type,
                        nationality=message.platform.nationality if message.platform.nationality is not None else track.platform.nationality,
                    )
                else:
                    track.platform = message.platform
            if message.callsign is not None:
                track.callsign = message.callsign
            if message.heading_deg is not None:
                track.heading_deg = message.heading_deg
            if message.speed_kph is not None:
                track.speed_kph = message.speed_kph

            if message.track_number is not None:
                track.track_number = message.track_number

            # Merge message-specific fields (non-destructive: only overwrites
            # keys that the new message carries).
            if message.fields:
                track.fields.update(message.fields)

            track.last_updated = message.timestamp
            track.message_count += 1

            # Notify listeners — snapshot so listeners can't mutate the
            # live track or see later mutations through a stashed reference.
            snapshot = _snapshot(track)
            for listener in self._listeners:
                try:
                    listener(snapshot, message)
                except Exception:
                    listener_name = getattr(listener, "__qualname__", repr(listener))
                    logger.exception(
                        "Track update listener '%s' failed while processing "
                        "STN %d (%s message)",
                        listener_name, track.stn, message.msg_type,
                    )

            return snapshot

    def get_by_stn(self, stn: int) -> Track | None:
        """Look up a track by Source Track Number.

        Args:
            stn: The integer STN to search for (exact match).

        Returns:
            A snapshot of the matching ``Track``, or ``None`` if not found.
        """
        with self._lock:
            track = self._tracks.get(stn)
            return _snapshot(track) if track is not None else None

    def get_by_callsign(self, callsign: str) -> Track | None:
        """Look up a track by callsign (case-insensitive).

        Args:
            callsign: The callsign string to match (e.g. ``"RULDOG01"``).

        Returns:
            A snapshot of the first matching ``Track``, or ``None``. If
            multiple tracks share a callsign (shouldn't happen), returns
            the first found.
        """
        callsign_upper = callsign.upper()
        with self._lock:
            for track in self._tracks.values():
                if track.callsign and track.callsign.upper() == callsign_upper:
                    return _snapshot(track)
        return None

    def get_by_track_number(self, track_number: str) -> Track | None:
        """Look up a track by its 5-character alphanumeric track number.

        Args:
            track_number: The track number string (exact match).

        Returns:
            A snapshot of the matching ``Track``, or ``None``.
        """
        with self._lock:
            for track in self._tracks.values():
                if track.track_number == track_number:
                    return _snapshot(track)
        return None

    def find(self, query: str) -> Track | None:
        """Look up a track by any identifier — the CLI's universal search.

        Resolution order:
            1. Try as STN — 5-digit strings are parsed as octal (Link 16
               convention), all other numeric strings as decimal.
            2. Try as track number (exact string match).
            3. Try as callsign (case-insensitive).

        All strategies are tried under a single lock acquisition for
        atomicity and efficiency.

        Args:
            query: A user-supplied identifier string.

        Returns:
            A snapshot of the first matching ``Track``, or ``None``.
        """
        with self._lock:
            # Try as STN (integer)
            try:
                stn = int(query, 8) if len(query) == 5 else int(query)
                track = self._tracks.get(stn)
                if track is not None:
                    return _snapshot(track)
            except ValueError:
                pass

            # Try as track number
            for track in self._tracks.values():
                if track.track_number == query:
                    return _snapshot(track)

            # Try as callsign
            callsign_upper = query.upper()
            for track in self._tracks.values():
                if track.callsign and track.callsign.upper() == callsign_upper:
                    return _snapshot(track)

        return None

    def all_tracks(self) -> list[Track]:
        """Return a snapshot of all current tracks, sorted by last update.

        Tracks that have never been updated sort to the end (by STN).
        """
        with self._lock:
            tracks = [_snapshot(t) for t in self._tracks.values()]
        # Partition into updated and never-updated to avoid comparing
        # datetime with int (which raises TypeError).
        updated = [t for t in tracks if t.last_updated is not None]
        never_updated = [t for t in tracks if t.last_updated is None]
        updated.sort(key=lambda t: t.last_updated, reverse=True)  # type: ignore[arg-type]
        never_updated.sort(key=lambda t: t.stn)
        return updated + never_updated

    def __len__(self) -> int:
        with self._lock:
            return len(self._tracks)

    def __iter__(self) -> Iterator[Track]:
        return iter(self.all_tracks())
