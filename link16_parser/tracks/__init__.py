"""In-memory track database with optional TTL-based aging.

Maintains the most recent state for each tracked entity, keyed by STN.
Supports lookup by STN, track number, or callsign. Notifies registered
listeners on every track update and on aging transitions (ACTIVE ->
STALE -> DROPPED).

Track aging is opt-in: call ``start_aging()`` to begin periodic sweeps
that transition tracks based on time since last update. Configure TTLs
via constructor parameters (``stale_ttl``, ``drop_ttl``) or at runtime
via properties.

See ``database.py`` for full documentation.
"""

from link16_parser.tracks.database import TrackDatabase

__all__ = ["TrackDatabase"]
