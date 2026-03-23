"""Tests for TrackDatabase merge semantics and listener notifications."""

from __future__ import annotations

from datetime import datetime, timezone

from link16_parser.core.types import Identity, Link16Message, Track
from link16_parser.tracks.database import TrackDatabase

TS = datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
TS2 = datetime(2024, 3, 15, 12, 1, 0, tzinfo=timezone.utc)


def _msg(
    stn: int = 100,
    msg_type: str = "J2.2",
    timestamp: datetime = TS,
    callsign: str | None = None,
    identity: Identity | None = None,
) -> Link16Message:
    """Shorthand for constructing a Link16Message with overrides."""
    return Link16Message(
        msg_type=msg_type, stn=stn, timestamp=timestamp,
        callsign=callsign, identity=identity,
    )


class TestUpdate:
    def test_creates_new_track(self, track_db: TrackDatabase) -> None:
        track_db.update(_msg(stn=100))

        assert len(track_db) == 1
        track = track_db.get_by_stn(100)
        assert track is not None
        assert track.stn == 100
        assert track.message_count == 1
        assert track.last_updated == TS

    def test_merges_nondestructively(self, track_db: TrackDatabase) -> None:
        # First message sets callsign
        track_db.update(_msg(stn=100, callsign="VIPER01"))

        # Second message sets identity but not callsign
        track_db.update(_msg(
            stn=100, msg_type="J3.2", timestamp=TS2,
            identity=Identity.FRIEND,
        ))

        track = track_db.get_by_stn(100)
        assert track is not None
        assert track.callsign == "VIPER01"        # not clobbered
        assert track.identity == Identity.FRIEND   # set by second msg
        assert track.message_count == 2

    def test_overwrites_non_none_fields(self, track_db: TrackDatabase) -> None:
        track_db.update(_msg(stn=100, callsign="VIPER01"))
        track_db.update(_msg(stn=100, callsign="VIPER02", timestamp=TS2))

        track = track_db.get_by_stn(100)
        assert track is not None
        assert track.callsign == "VIPER02"

    def test_listener_receives_notification(self, track_db: TrackDatabase) -> None:
        received: list[tuple[Track, Link16Message]] = []
        track_db.on_update(lambda t, m: received.append((t, m)))

        msg = _msg(stn=100)
        track_db.update(msg)

        assert len(received) == 1
        track, message = received[0]
        assert track.stn == 100
        assert message is msg


class TestFind:
    def test_find_by_stn(self, track_db: TrackDatabase) -> None:
        track_db.update(_msg(stn=100))

        assert track_db.find("100") is not None
        assert track_db.find("999") is None

    def test_find_by_callsign(self, track_db: TrackDatabase) -> None:
        track_db.update(_msg(stn=100, callsign="VIPER01"))

        assert track_db.find("VIPER01") is not None
        assert track_db.find("viper01") is not None   # case-insensitive
        assert track_db.find("EAGLE01") is None

    def test_find_by_track_number(self, track_db: TrackDatabase) -> None:
        msg = _msg(stn=100)
        msg.fields["track_number"] = "A1234"
        track_db.update(msg)

        assert track_db.find("A1234") is not None
