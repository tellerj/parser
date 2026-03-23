"""In-memory track database.

Maintains the most recent state for each tracked entity, keyed by STN.
See ``database.py`` for full documentation.
"""

from link16_parser.tracks.database import TrackDatabase

__all__ = ["TrackDatabase"]
