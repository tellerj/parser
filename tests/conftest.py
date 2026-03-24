"""Shared pytest fixtures for link16-parser tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from link16_parser.link16 import JWordParser, build_parser
from link16_parser.tracks import TrackDatabase

FIXTURES_DIR = str(Path(__file__).parent / "fixtures")


@pytest.fixture
def track_db() -> TrackDatabase:
    """A fresh, empty TrackDatabase."""
    return TrackDatabase()


@pytest.fixture
def jword_parser() -> JWordParser:
    """A JWordParser with test fixture decoders registered."""
    return build_parser(definitions_dir=FIXTURES_DIR)
