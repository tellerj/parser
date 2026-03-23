"""Shared pytest fixtures for link16-parser tests."""

from __future__ import annotations

import pytest

from link16_parser.__main__ import build_jword_parser
from link16_parser.link16.parser import JWordParser
from link16_parser.tracks.database import TrackDatabase


@pytest.fixture
def track_db() -> TrackDatabase:
    """A fresh, empty TrackDatabase."""
    return TrackDatabase()


@pytest.fixture
def jword_parser() -> JWordParser:
    """A JWordParser with all standard decoders registered."""
    return build_jword_parser()
