"""Tests for the output layer: coords, tacrep, and nineline formatters."""

from __future__ import annotations

from datetime import datetime, timezone

from link16_parser.core.interfaces import OutputFormatter
from link16_parser.core.types import Identity, Link16Message, PlatformId, Position, Track, TrackStatus
from link16_parser.output.coords import (
    decimal_to_military_lat,
    decimal_to_military_lon,
    format_dtg,
    position_to_lm,
)
from link16_parser.output.csv_format import CsvFormatter
from link16_parser.output.json_format import JsonFormatter
from link16_parser.output.nineline_format import NineLineFormatter
from link16_parser.output.tacrep_format import TacrepFormatter


# ---------------------------------------------------------------------------
# Coordinate conversion
# ---------------------------------------------------------------------------


class TestDecimalToMilitaryLat:
    def test_positive_north(self) -> None:
        assert decimal_to_military_lat(36.25) == "3615N"

    def test_negative_south(self) -> None:
        assert decimal_to_military_lat(-33.5) == "3330S"

    def test_zero_is_north(self) -> None:
        assert decimal_to_military_lat(0.0) == "0000N"

    def test_whole_degrees(self) -> None:
        assert decimal_to_military_lat(45.0) == "4500N"

    def test_rounding_up(self) -> None:
        # 36.999... degrees — minutes should round to 60, which rolls over
        assert decimal_to_military_lat(36.999) == "3700N"

    def test_rounding_boundary(self) -> None:
        # 35.9999 → 59.994 minutes → rounds to 60 → should be 3600N
        assert decimal_to_military_lat(35.9999) == "3600N"

    def test_small_fractional(self) -> None:
        # 30.0833... → 30°05'
        assert decimal_to_military_lat(30.0833) == "3005N"


class TestDecimalToMilitaryLon:
    def test_negative_west(self) -> None:
        assert decimal_to_military_lon(-115.75) == "11545W"

    def test_positive_east(self) -> None:
        assert decimal_to_military_lon(5.5) == "00530E"

    def test_zero_is_east(self) -> None:
        assert decimal_to_military_lon(0.0) == "00000E"

    def test_rounding_up(self) -> None:
        assert decimal_to_military_lon(-79.999) == "08000W"

    def test_three_digit_degrees(self) -> None:
        assert decimal_to_military_lon(120.5) == "12030E"


class TestPositionToLm:
    def test_combined(self) -> None:
        pos = Position(36.25, -115.75)
        assert position_to_lm(pos) == "3615N11545W"

    def test_with_altitude_ignored(self) -> None:
        pos = Position(30.0, -80.0, alt_m=5000.0)
        assert position_to_lm(pos) == "3000N08000W"


# ---------------------------------------------------------------------------
# DTG formatting
# ---------------------------------------------------------------------------


class TestFormatDtg:
    def test_none_returns_unk(self) -> None:
        assert format_dtg(None) == "UNK"

    def test_formats_correctly(self) -> None:
        ts = datetime(2024, 3, 15, 14, 30, 0, tzinfo=timezone.utc)
        assert format_dtg(ts) == "151430Z"

    def test_zero_padded(self) -> None:
        ts = datetime(2024, 1, 5, 3, 7, 0, tzinfo=timezone.utc)
        assert format_dtg(ts) == "050307Z"

    def test_non_utc_converted(self) -> None:
        # EST is UTC-5: 10:00 EST = 15:00 UTC
        from datetime import timedelta
        est = timezone(timedelta(hours=-5))
        ts = datetime(2024, 3, 15, 10, 30, 0, tzinfo=est)
        assert format_dtg(ts) == "151530Z"

    def test_naive_datetime_assumed_utc(self) -> None:
        ts = datetime(2024, 3, 15, 14, 30, 0)
        assert format_dtg(ts) == "151430Z"


# ---------------------------------------------------------------------------
# TacrepFormatter
# ---------------------------------------------------------------------------


class TestTacrepFormatter:
    def _make_track(self, **kwargs: object) -> Track:
        defaults: dict[str, object] = {
            "stn": 12345,
            "position": Position(30.25, -80.5, alt_m=2500.0),
            "identity": Identity.HOSTILE,
            "platform": PlatformId(
                generic_type="FTR",
                specific_type="F16C",
                nationality="US",
            ),
            "callsign": "RULDOG01",
            "heading_deg": 200.0,
            "speed_kph": 650.0,
            "track_number": "A1234",
            "last_updated": datetime(2024, 3, 31, 15, 0, 0, tzinfo=timezone.utc),
            "message_count": 5,
        }
        defaults.update(kwargs)
        return Track(**defaults)  # type: ignore[arg-type]

    def test_name(self) -> None:
        fmt = TacrepFormatter()
        assert fmt.name == "TACREP"

    def test_full_track(self) -> None:
        fmt = TacrepFormatter(originator="CTF124", classification="SECRET")
        track = self._make_track()
        result = fmt.format(track)
        lines = result.split("\n")

        assert lines[0] == "SECRET"
        assert lines[1] == "MSGID/TACREP/CTF124//"
        assert "AIROP/" in lines[2]
        assert "311500Z" in lines[2]
        assert "/1/" in lines[2]
        assert "/US/" in lines[2]
        assert "/FTR/" in lines[2]
        assert "/F16C/" in lines[2]
        assert "TN:A1234" in lines[2]
        assert "LM:3015N08030W" in lines[2]
        assert "CRS:200" in lines[3]
        assert "SPD:650KPH" in lines[3]
        assert "ALT:2500M" in lines[3]
        assert "AMPN/RULDOG01/ID:HOSTILE//" == lines[4]

    def test_minimal_track(self) -> None:
        fmt = TacrepFormatter()
        track = Track(stn=100)
        result = fmt.format(track)
        lines = result.split("\n")

        assert lines[0] == "UNCLAS"
        assert "UNK" in lines[2]  # DTG
        assert "LM:UNK" in lines[2]
        assert "AMPN/NO AMPLIFYING DATA//" == lines[3]
        assert "AMPN//" == lines[4]

    def test_no_callsign(self) -> None:
        fmt = TacrepFormatter()
        track = self._make_track(callsign=None)
        result = fmt.format(track)
        lines = result.split("\n")
        assert lines[4] == "AMPN/ID:HOSTILE//"

    def test_no_speed_heading(self) -> None:
        fmt = TacrepFormatter()
        track = self._make_track(heading_deg=None, speed_kph=None)
        result = fmt.format(track)
        lines = result.split("\n")
        # Line 4 should still have ALT
        assert "ALT:2500M" in lines[3]
        assert "CRS:" not in lines[3]

    def test_stale_status_in_ampn(self) -> None:
        fmt = TacrepFormatter()
        track = self._make_track(status=TrackStatus.STALE)
        result = fmt.format(track)
        lines = result.split("\n")
        assert "AMPN/RULDOG01/ID:HOSTILE/STATUS:STALE//" == lines[4]

    def test_dropped_status_in_ampn(self) -> None:
        fmt = TacrepFormatter()
        track = self._make_track(status=TrackStatus.DROPPED, callsign=None)
        result = fmt.format(track)
        lines = result.split("\n")
        assert "AMPN/ID:HOSTILE/STATUS:DROPPED//" == lines[4]

    def test_active_status_omitted(self) -> None:
        fmt = TacrepFormatter()
        track = self._make_track()
        result = fmt.format(track)
        assert "STATUS:" not in result

    def test_identity_in_ampn(self) -> None:
        fmt = TacrepFormatter()
        track = self._make_track()
        result = fmt.format(track)
        lines = result.split("\n")
        assert "ID:HOSTILE" in lines[4]

    def test_no_identity(self) -> None:
        fmt = TacrepFormatter()
        track = self._make_track(identity=None, callsign=None)
        result = fmt.format(track)
        lines = result.split("\n")
        assert "ID:" not in lines[4]

    def test_fields_in_ampn(self) -> None:
        fmt = TacrepFormatter()
        track = self._make_track(fields={"fuel": "BINGO", "wpn": 2})
        result = fmt.format(track)
        lines = result.split("\n")
        assert "FUEL:BINGO" in lines[4]
        assert "WPN:2" in lines[4]

    def test_fields_skips_complex_values(self) -> None:
        fmt = TacrepFormatter()
        track = self._make_track(fields={"nested": {"a": 1}, "simple": "OK"})
        result = fmt.format(track)
        lines = result.split("\n")
        assert "SIMPLE:OK" in lines[4]
        assert "NESTED" not in lines[4]


# ---------------------------------------------------------------------------
# NineLineFormatter
# ---------------------------------------------------------------------------


class TestNineLineFormatter:
    def _make_track(self, **kwargs: object) -> Track:
        defaults: dict[str, object] = {
            "stn": 12345,
            "position": Position(30.25, -80.5, alt_m=2500.0),
            "identity": Identity.HOSTILE,
            "platform": PlatformId(
                generic_type="FTR",
                specific_type="F16C",
                nationality="US",
            ),
            "callsign": "RULDOG01",
            "heading_deg": 200.0,
            "speed_kph": 650.0,
            "track_number": "A1234",
            "last_updated": datetime(2024, 3, 31, 15, 0, 0, tzinfo=timezone.utc),
            "message_count": 5,
        }
        defaults.update(kwargs)
        return Track(**defaults)  # type: ignore[arg-type]

    def test_name(self) -> None:
        fmt = NineLineFormatter()
        assert fmt.name == "9-LINE"

    def test_full_track(self) -> None:
        fmt = NineLineFormatter()
        track = self._make_track()
        result = fmt.format(track)
        lines = result.split("\n")

        assert len(lines) == 9
        assert lines[0] == "LINE 1: A1234"
        assert lines[1] == "LINE 2: F16C"
        assert lines[2] == "LINE 3: RULDOG01"
        assert lines[3] == "LINE 4: 3015N08030W"
        assert lines[4] == "LINE 5: 2500M"
        assert lines[5] == "LINE 6: 200"
        assert lines[6] == "LINE 7: 650KPH"
        assert lines[7] == "LINE 8: 311500Z"
        assert lines[8] == "LINE 9: ID:HOSTILE"

    def test_minimal_track(self) -> None:
        fmt = NineLineFormatter()
        track = Track(stn=100)
        result = fmt.format(track)
        lines = result.split("\n")

        assert lines[0] == "LINE 1: 100"  # STN fallback
        assert lines[1] == "LINE 2: UNK"
        assert lines[2] == "LINE 3: UNK"
        assert lines[3] == "LINE 4: UNK"
        assert lines[4] == "LINE 5: UNK"
        assert lines[5] == "LINE 6: UNK"
        assert lines[6] == "LINE 7: UNK"
        assert lines[7] == "LINE 8: UNK"
        assert lines[8] == "LINE 9: ID:UNK"

    def test_generic_type_fallback(self) -> None:
        fmt = NineLineFormatter()
        track = self._make_track(
            platform=PlatformId(generic_type="BMR", specific_type=None),
        )
        result = fmt.format(track)
        lines = result.split("\n")
        assert lines[1] == "LINE 2: BMR"

    def test_stale_status_in_line9(self) -> None:
        fmt = NineLineFormatter()
        track = self._make_track(status=TrackStatus.STALE)
        result = fmt.format(track)
        lines = result.split("\n")
        assert lines[8] == "LINE 9: ID:HOSTILE STATUS:STALE"

    def test_active_status_omitted(self) -> None:
        fmt = NineLineFormatter()
        track = self._make_track()
        result = fmt.format(track)
        lines = result.split("\n")
        assert lines[8] == "LINE 9: ID:HOSTILE"

    def test_fields_in_line9(self) -> None:
        fmt = NineLineFormatter()
        track = self._make_track(fields={"fuel": "BINGO"})
        result = fmt.format(track)
        lines = result.split("\n")
        assert "FUEL:BINGO" in lines[8]

    def test_fields_skips_complex_values(self) -> None:
        fmt = NineLineFormatter()
        track = self._make_track(fields={"nested": [1, 2], "simple": 42})
        result = fmt.format(track)
        lines = result.split("\n")
        assert "SIMPLE:42" in lines[8]
        assert "NESTED" not in lines[8]


# ---------------------------------------------------------------------------
# JsonFormatter
# ---------------------------------------------------------------------------


class TestJsonFormatter:
    def _make_track(self, **kwargs: object) -> Track:
        defaults: dict[str, object] = {
            "stn": 12345,
            "position": Position(30.25, -80.5, alt_m=2500.0),
            "identity": Identity.HOSTILE,
            "platform": PlatformId(
                generic_type="FTR",
                specific_type="F16C",
                nationality="US",
            ),
            "callsign": "RULDOG01",
            "heading_deg": 200.0,
            "speed_kph": 650.0,
            "track_number": "A1234",
            "last_updated": datetime(2024, 3, 31, 15, 0, 0, tzinfo=timezone.utc),
            "message_count": 5,
        }
        defaults.update(kwargs)
        return Track(**defaults)  # type: ignore[arg-type]

    def test_name(self) -> None:
        fmt = JsonFormatter()
        assert fmt.name == "JSON"

    def test_full_track_is_valid_json(self) -> None:
        import json
        fmt = JsonFormatter()
        track = self._make_track()
        result = fmt.format(track)
        obj = json.loads(result)
        assert obj["stn"] == 12345
        assert obj["callsign"] == "RULDOG01"
        assert obj["identity"] == "HOSTILE"
        assert obj["status"] == "ACTIVE"
        assert obj["position"]["lat"] == 30.25
        assert obj["position"]["lon"] == -80.5
        assert obj["position"]["alt_m"] == 2500.0
        assert obj["platform"]["specific_type"] == "F16C"
        assert obj["platform"]["nationality"] == "US"
        assert obj["heading_deg"] == 200.0
        assert obj["speed_kph"] == 650.0
        assert obj["track_number"] == "A1234"
        assert obj["message_count"] == 5
        assert obj["last_updated"] == "2024-03-31T15:00:00+00:00"

    def test_minimal_track_nulls(self) -> None:
        import json
        fmt = JsonFormatter()
        track = Track(stn=100)
        obj = json.loads(fmt.format(track))
        assert obj["stn"] == 100
        assert obj["position"] is None
        assert obj["identity"] is None
        assert obj["platform"] is None
        assert obj["callsign"] is None
        assert obj["last_updated"] is None
        assert "fields" not in obj  # empty fields dict omitted

    def test_fields_included_when_present(self) -> None:
        import json
        fmt = JsonFormatter()
        track = self._make_track(fields={"fuel": "BINGO", "wpn": 2})
        obj = json.loads(fmt.format(track))
        assert obj["fields"]["fuel"] == "BINGO"
        assert obj["fields"]["wpn"] == 2

    def test_single_line_output(self) -> None:
        fmt = JsonFormatter()
        track = self._make_track()
        result = fmt.format(track)
        assert "\n" not in result


# ---------------------------------------------------------------------------
# CsvFormatter
# ---------------------------------------------------------------------------


class TestCsvFormatter:
    def _make_track(self, **kwargs: object) -> Track:
        defaults: dict[str, object] = {
            "stn": 12345,
            "position": Position(30.25, -80.5, alt_m=2500.0),
            "identity": Identity.HOSTILE,
            "platform": PlatformId(
                generic_type="FTR",
                specific_type="F16C",
                nationality="US",
            ),
            "callsign": "RULDOG01",
            "heading_deg": 200.0,
            "speed_kph": 650.0,
            "track_number": "A1234",
            "last_updated": datetime(2024, 3, 31, 15, 0, 0, tzinfo=timezone.utc),
            "message_count": 5,
        }
        defaults.update(kwargs)
        return Track(**defaults)  # type: ignore[arg-type]

    def test_name(self) -> None:
        fmt = CsvFormatter()
        assert fmt.name == "CSV"

    def test_header_returns_column_names(self) -> None:
        fmt = CsvFormatter()
        header = fmt.header()
        assert header.startswith("stn,")
        assert "callsign" in header
        assert "message_count" in header

    def test_format_returns_data_only(self) -> None:
        fmt = CsvFormatter()
        track = self._make_track()
        result = fmt.format(track)
        assert "\n" not in result
        assert result.startswith("12345,")

    def test_stateless_across_calls(self) -> None:
        fmt = CsvFormatter()
        track = self._make_track()
        first = fmt.format(track)
        second = fmt.format(track)
        assert first == second  # no state change between calls

    def test_minimal_track_empty_fields(self) -> None:
        fmt = CsvFormatter()
        track = Track(stn=100)
        row = fmt.format(track).split(",")
        assert row[0] == "100"  # stn
        assert row[2] == ""  # track_number is None -> empty
        assert row[3] == ""  # callsign is None -> empty

    def test_full_track_column_values(self) -> None:
        fmt = CsvFormatter()
        track = self._make_track()
        row = fmt.format(track).split(",")
        assert row[0] == "12345"   # stn
        assert row[1] == "ACTIVE"  # status
        assert row[2] == "A1234"   # track_number
        assert row[3] == "RULDOG01"  # callsign
        assert row[4] == "30.25"   # lat
        assert row[5] == "-80.5"   # lon
        assert row[6] == "2500.0"  # alt_m
        assert row[7] == "HOSTILE"  # identity
        assert row[8] == "FTR"     # generic_type
        assert row[9] == "F16C"    # specific_type
        assert row[10] == "US"     # nationality
        assert row[11] == "200.0"  # heading_deg
        assert row[12] == "650.0"  # speed_kph
        assert row[14] == "5"      # message_count

    def test_value_with_comma_is_quoted(self) -> None:
        fmt = CsvFormatter()
        track = self._make_track(callsign="ALPHA,BRAVO")
        result = fmt.format(track)
        assert '"ALPHA,BRAVO"' in result


# ---------------------------------------------------------------------------
# Coordinate utilities — haversine, bearing, conversions
# ---------------------------------------------------------------------------


class TestHaversineDistance:
    def test_same_point_is_zero(self) -> None:
        from link16_parser.output.coords import haversine_distance_nm
        assert haversine_distance_nm(0, 0, 0, 0) == 0.0

    def test_equator_one_degree_longitude(self) -> None:
        from link16_parser.output.coords import haversine_distance_nm
        dist = haversine_distance_nm(0, 0, 0, 1)
        # 1 degree at equator ≈ 60 NM
        assert 59.5 < dist < 60.5

    def test_known_distance(self) -> None:
        from link16_parser.output.coords import haversine_distance_nm
        # New York (40.7128, -74.0060) to London (51.5074, -0.1278)
        dist = haversine_distance_nm(40.7128, -74.0060, 51.5074, -0.1278)
        # Known ≈ 2999 NM
        assert 2990 < dist < 3010


class TestInitialBearing:
    def test_due_north(self) -> None:
        from link16_parser.output.coords import initial_bearing_deg
        bearing = initial_bearing_deg(0, 0, 1, 0)
        assert abs(bearing - 0) < 0.1

    def test_due_east(self) -> None:
        from link16_parser.output.coords import initial_bearing_deg
        bearing = initial_bearing_deg(0, 0, 0, 1)
        assert abs(bearing - 90) < 0.1

    def test_due_south(self) -> None:
        from link16_parser.output.coords import initial_bearing_deg
        bearing = initial_bearing_deg(0, 0, -1, 0)
        assert abs(bearing - 180) < 0.1

    def test_due_west(self) -> None:
        from link16_parser.output.coords import initial_bearing_deg
        bearing = initial_bearing_deg(0, 0, 0, -1)
        assert abs(bearing - 270) < 0.1


class TestMetersToFlightLevel:
    def test_none_returns_none(self) -> None:
        from link16_parser.output.coords import meters_to_flight_level
        assert meters_to_flight_level(None) is None

    def test_25000_feet(self) -> None:
        from link16_parser.output.coords import meters_to_flight_level
        # 7620m ≈ 25000 ft → FL250
        assert meters_to_flight_level(7620) == "FL250"

    def test_zero(self) -> None:
        from link16_parser.output.coords import meters_to_flight_level
        assert meters_to_flight_level(0) == "FL000"


class TestKphToKnots:
    def test_none_returns_none(self) -> None:
        from link16_parser.output.coords import kph_to_knots
        assert kph_to_knots(None) is None

    def test_known_conversion(self) -> None:
        from link16_parser.output.coords import kph_to_knots
        # 1852 kph = 1000 knots
        result = kph_to_knots(1852)
        assert result is not None
        assert abs(result - 1000) < 0.01


# ---------------------------------------------------------------------------
# Bullseye formatter
# ---------------------------------------------------------------------------


class TestBullseyeFormatter:
    @staticmethod
    def _make_track(**overrides: object) -> Track:
        defaults: dict[str, object] = {
            "stn": 12345,
            "status": TrackStatus.ACTIVE,
            "track_number": "A1234",
            "callsign": "VIPER01",
            "position": Position(37.5, -115.5, 7620.0),
            "identity": Identity.FRIEND,
            "platform": PlatformId("FTR", "F16C", "US"),
            "heading_deg": 90.0,
            "speed_kph": 833.44,  # ~450 knots
            "last_updated": datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc),
            "message_count": 5,
        }
        defaults.update(overrides)
        return Track(**defaults)  # type: ignore[arg-type]

    def test_full_output_contains_all_parts(self) -> None:
        from link16_parser.output.bullseye_format import BullseyeFormatter
        fmt = BullseyeFormatter(bull_lat=37.0, bull_lon=-116.0)
        track = self._make_track()
        result = fmt.format(track)
        assert result.startswith("STN:12345")
        assert "BULLSEYE" in result
        assert "FL" in result
        assert "HDG:090" in result
        assert "SPD:" in result
        assert "KT" in result
        assert "ID:FRIEND" in result
        assert "[VIPER01]" in result
        # ACTIVE status should NOT appear
        assert "STATUS:" not in result

    def test_no_position(self) -> None:
        from link16_parser.output.bullseye_format import BullseyeFormatter
        fmt = BullseyeFormatter(bull_lat=37.0, bull_lon=-116.0)
        track = self._make_track(position=None)
        result = fmt.format(track)
        assert "BULLSEYE ---/---" in result
        assert "FL" not in result

    def test_no_altitude(self) -> None:
        from link16_parser.output.bullseye_format import BullseyeFormatter
        fmt = BullseyeFormatter(bull_lat=37.0, bull_lon=-116.0)
        track = self._make_track(position=Position(37.5, -115.5))
        result = fmt.format(track)
        assert "BULLSEYE" in result
        assert "FL" not in result

    def test_none_fields_omitted(self) -> None:
        from link16_parser.output.bullseye_format import BullseyeFormatter
        fmt = BullseyeFormatter(bull_lat=37.0, bull_lon=-116.0)
        track = self._make_track(
            heading_deg=None, speed_kph=None, identity=None, callsign=None,
        )
        result = fmt.format(track)
        assert "HDG:" not in result
        assert "SPD:" not in result
        assert "ID:" not in result
        assert "[" not in result

    def test_stale_status_shown(self) -> None:
        from link16_parser.output.bullseye_format import BullseyeFormatter
        fmt = BullseyeFormatter(bull_lat=37.0, bull_lon=-116.0)
        track = self._make_track(status=TrackStatus.STALE)
        result = fmt.format(track)
        assert "STATUS:STALE" in result

    def test_active_status_omitted(self) -> None:
        from link16_parser.output.bullseye_format import BullseyeFormatter
        fmt = BullseyeFormatter(bull_lat=37.0, bull_lon=-116.0)
        track = self._make_track(status=TrackStatus.ACTIVE)
        result = fmt.format(track)
        assert "STATUS:" not in result

    def test_fields_rendered(self) -> None:
        from link16_parser.output.bullseye_format import BullseyeFormatter
        fmt = BullseyeFormatter(bull_lat=37.0, bull_lon=-116.0)
        track = self._make_track(fields={"mission": "CAP", "fuel": 85})
        result = fmt.format(track)
        assert "MISSION:CAP" in result
        assert "FUEL:85" in result

    def test_reference_property(self) -> None:
        from link16_parser.output.bullseye_format import BullseyeFormatter
        fmt = BullseyeFormatter(bull_lat=10.0, bull_lon=20.0)
        lat, lon = fmt.reference
        assert lat == 10.0
        assert lon == 20.0

    def test_build_formatters_no_bullseye_by_default(self) -> None:
        from link16_parser.output import build_formatters
        formatters = build_formatters()
        assert "BULLSEYE" not in formatters

    def test_build_formatters_bullseye_when_coords_provided(self) -> None:
        from link16_parser.output import build_formatters
        formatters = build_formatters(bullseye_lat=50.0, bullseye_lon=10.0)
        assert "BULLSEYE" in formatters
        ref = getattr(formatters["BULLSEYE"], "reference", None)
        assert ref == (50.0, 10.0)


# ---------------------------------------------------------------------------
# Shell helpers
# ---------------------------------------------------------------------------


def _run_shell(
    commands: list[str],
    tracks: list[Track] | None = None,
    formatters: dict[str, OutputFormatter] | None = None,
) -> str:
    """Run shell commands against an in-memory DB and return captured output."""
    import io
    from link16_parser.cli.shell import InteractiveShell
    from link16_parser.output import build_formatters
    from link16_parser.tracks.database import TrackDatabase

    db = TrackDatabase()
    if tracks:
        for t in tracks:
            msg = Link16Message(
                stn=t.stn,
                msg_type="J3.2",
                timestamp=t.last_updated or datetime(2025, 1, 1, tzinfo=timezone.utc),
                position=t.position,
                identity=t.identity,
                platform=t.platform,
                callsign=t.callsign,
                heading_deg=t.heading_deg,
                speed_kph=t.speed_kph,
                track_number=t.track_number,
                fields=dict(t.fields) if t.fields else {},
            )
            db.update(msg)

    if formatters is None:
        formatters = build_formatters()
    inp = io.StringIO("\n".join(commands) + "\n")
    out = io.StringIO()
    shell = InteractiveShell(
        track_db=db, formatters=formatters,
        input_stream=inp, output_stream=out,
    )
    shell.run()
    return out.getvalue()


# ---------------------------------------------------------------------------
# Shell — bullseye interactive flow
# ---------------------------------------------------------------------------


class TestShellBullseyeFlow:
    """Tests for the interactive bullseye UX in the CLI shell."""

    def test_bullseye_without_ref_prompts_to_set(self) -> None:
        output = _run_shell(["bullseye 12345", "quit"])
        assert "No bullseye reference point set" in output
        assert "bullseye set LAT,LON" in output

    def test_bullseye_set_registers_formatter(self) -> None:
        output = _run_shell([
            "bullseye set 37.0,-116.0",
            "quit",
        ])
        assert "Bullseye reference set to: 37.0000, -116.0000" in output

    def test_bullseye_set_then_use(self) -> None:
        # Set ref, then query a track (won't find it, but should not say "not available")
        output = _run_shell([
            "bullseye set 37.0,-116.0",
            "bullseye 12345",
            "quit",
        ])
        assert "Bullseye reference set to" in output
        assert "No bullseye reference point set" not in output
        # Track won't exist, so we get "No track found"
        assert "No track found" in output

    def test_bullseye_set_invalid_coords(self) -> None:
        output = _run_shell(["bullseye set abc", "quit"])
        assert "Invalid coordinates" in output

    def test_bullseye_set_no_args(self) -> None:
        output = _run_shell(["bullseye set", "quit"])
        assert "Usage: bullseye set LAT,LON" in output

    def test_format_bullseye_without_ref_guides_user(self) -> None:
        output = _run_shell(["format bullseye", "quit"])
        assert "requires a reference point" in output
        assert "bullseye set LAT,LON" in output

    def test_format_list_shows_bullseye_hint_when_unset(self) -> None:
        output = _run_shell(["format", "quit"])
        assert "BULLSEYE (requires: bullseye set LAT,LON)" in output

    def test_format_list_shows_bullseye_normally_when_set(self) -> None:
        from link16_parser.output import build_formatters
        formatters = build_formatters(bullseye_lat=37.0, bullseye_lon=-116.0)
        output = _run_shell(["format", "quit"], formatters=formatters)
        # Should show BULLSEYE without the hint
        assert "BULLSEYE" in output
        assert "(requires:" not in output

    def test_bullseye_no_args_shows_ref_and_usage(self) -> None:
        from link16_parser.output import build_formatters
        formatters = build_formatters(bullseye_lat=37.0, bullseye_lon=-116.0)
        output = _run_shell(["bullseye", "quit"], formatters=formatters)
        assert "Bullseye reference: 37.0000, -116.0000" in output
        assert "Usage: bullseye <id>" in output

    def test_format_bullseye_after_set(self) -> None:
        output = _run_shell([
            "bullseye set 40.0,-80.0",
            "format bullseye",
            "quit",
        ])
        assert "Default format set to: BULLSEYE" in output


# ---------------------------------------------------------------------------
# Shell — command tests
# ---------------------------------------------------------------------------


class TestShellCommands:
    """Tests for CLI shell commands: list, search, status, format, info, etc."""

    @staticmethod
    def _sample_tracks() -> list[Track]:
        """Build a small set of test tracks."""
        return [
            Track(
                stn=100,
                track_number="T0100",
                callsign="VIPER01",
                identity=Identity.FRIEND,
                platform=PlatformId(generic_type="FTR", specific_type="F16C", nationality="US"),
                position=Position(lat=36.0, lon=-115.0, alt_m=7620.0),
                heading_deg=90.0,
                speed_kph=900.0,
                last_updated=datetime(2025, 3, 15, 14, 30, 0, tzinfo=timezone.utc),
                message_count=1,
            ),
            Track(
                stn=200,
                track_number="T0200",
                callsign="SNAKE11",
                identity=Identity.HOSTILE,
                platform=PlatformId(generic_type="FTR", specific_type="SU35", nationality="RU"),
                position=Position(lat=37.0, lon=-116.0, alt_m=9000.0),
                heading_deg=270.0,
                speed_kph=1100.0,
                last_updated=datetime(2025, 3, 15, 14, 31, 0, tzinfo=timezone.utc),
                message_count=1,
                status=TrackStatus.STALE,
            ),
            Track(
                stn=300,
                callsign="TEXACO1",
                identity=Identity.FRIEND,
                platform=PlatformId(generic_type="TNK", specific_type="KC135", nationality="US"),
                last_updated=datetime(2025, 3, 15, 14, 25, 0, tzinfo=timezone.utc),
                message_count=1,
            ),
        ]

    # -- list --

    def test_list_no_tracks(self) -> None:
        output = _run_shell(["list", "quit"])
        assert "No tracks." in output

    def test_list_shows_tracks_and_count(self) -> None:
        output = _run_shell(["list", "quit"], tracks=self._sample_tracks())
        assert "VIPER01" in output
        assert "SNAKE11" in output
        assert "TEXACO1" in output
        assert "--- 3 tracks ---" in output

    def test_list_shows_header(self) -> None:
        output = _run_shell(["list", "quit"], tracks=self._sample_tracks())
        assert "STN" in output
        assert "CALLSIGN" in output
        assert "STATUS" in output

    def test_list_singular_track_count(self) -> None:
        tracks = [self._sample_tracks()[0]]
        output = _run_shell(["list", "quit"], tracks=tracks)
        assert "--- 1 track ---" in output

    # -- search --

    def test_search_by_identity(self) -> None:
        output = _run_shell(["search hostile", "quit"], tracks=self._sample_tracks())
        assert "SNAKE11" in output
        assert "VIPER01" not in output
        assert "--- 1 track ---" in output

    def test_search_by_callsign(self) -> None:
        output = _run_shell(["search viper", "quit"], tracks=self._sample_tracks())
        assert "VIPER01" in output
        assert "SNAKE11" not in output

    def test_search_by_platform_type(self) -> None:
        output = _run_shell(["search F16C", "quit"], tracks=self._sample_tracks())
        assert "VIPER01" in output
        assert "SNAKE11" not in output

    def test_search_by_status(self) -> None:
        # All tracks inserted via update() start as ACTIVE
        output = _run_shell(["search active", "quit"], tracks=self._sample_tracks())
        assert "VIPER01" in output
        assert "--- 3 tracks ---" in output

    def test_search_no_results(self) -> None:
        output = _run_shell(["search BOGUS", "quit"], tracks=self._sample_tracks())
        assert "No tracks matching 'BOGUS'" in output

    def test_search_no_args(self) -> None:
        output = _run_shell(["search", "quit"])
        assert "Usage: search <query>" in output

    # -- status --

    def test_status_with_tracks(self) -> None:
        output = _run_shell(["status", "quit"], tracks=self._sample_tracks())
        assert "Tracks:" in output
        assert "3" in output
        assert "Identity:" in output
        assert "friend" in output
        assert "hostile" in output
        assert "Format:" in output

    def test_status_no_tracks(self) -> None:
        output = _run_shell(["status", "quit"])
        assert "Tracks:   0" in output

    def test_status_shows_bullseye_when_set(self) -> None:
        from link16_parser.output import build_formatters
        fmts = build_formatters(bullseye_lat=37.0, bullseye_lon=-116.0)
        output = _run_shell(["status", "quit"], formatters=fmts)
        assert "Bullseye: 37.0000, -116.0000" in output

    # -- format --

    def test_format_alias_9line(self) -> None:
        output = _run_shell(["format 9line", "quit"])
        assert "Default format set to: 9-LINE" in output

    def test_format_alias_nineline(self) -> None:
        output = _run_shell(["format nineline", "quit"])
        assert "Default format set to: 9-LINE" in output

    def test_format_unknown(self) -> None:
        output = _run_shell(["format BOGUS", "quit"])
        assert "Unknown format: BOGUS" in output

    # -- report --

    def test_report_uses_current_format(self) -> None:
        output = _run_shell(
            ["format json", "report 100", "quit"],
            tracks=self._sample_tracks(),
        )
        assert "Default format set to: JSON" in output
        assert '"stn":100' in output

    # -- info --

    def test_info_shows_all_fields(self) -> None:
        output = _run_shell(["info 100", "quit"], tracks=self._sample_tracks())
        assert "STN:" in output
        assert "100" in output
        assert "VIPER01" in output
        assert "FRIEND" in output
        assert "F16C" in output

    def test_info_no_args(self) -> None:
        output = _run_shell(["info", "quit"])
        assert "Usage: info <identifier>" in output

    def test_info_not_found(self) -> None:
        output = _run_shell(["info 99999", "quit"])
        assert "No track found" in output

    # -- help --

    def test_help_contains_all_commands(self) -> None:
        output = _run_shell(["help", "quit"])
        for cmd in ["list", "search", "status", "report", "tacrep", "9line",
                     "json", "csv", "bullseye", "info", "export", "config",
                     "debug", "format", "help", "quit"]:
            assert cmd in output

    def test_help_shows_available_formats(self) -> None:
        output = _run_shell(["help", "quit"])
        assert "TACREP" in output
        assert "JSON" in output

    def test_help_shows_identifier_resolution(self) -> None:
        output = _run_shell(["help", "quit"])
        assert "octal" in output
        assert "case-insensitive" in output

    # -- error handling --

    def test_unknown_command(self) -> None:
        output = _run_shell(["boguscmd", "quit"])
        assert "Unknown command: boguscmd" in output

    def test_shlex_parse_error(self) -> None:
        output = _run_shell(["report 'unmatched", "quit"])
        assert "Parse error" in output
        assert "unmatched quotes" in output.lower() or "No closing quotation" in output

    # -- quit / EOF --

    def test_quit_exits(self) -> None:
        output = _run_shell(["quit"])
        # Should not hang — if we get output, the loop exited
        assert "Link 16 Parser" in output

    def test_eof_exits(self) -> None:
        # Empty input triggers EOF
        import io
        from link16_parser.cli.shell import InteractiveShell
        from link16_parser.output import build_formatters
        from link16_parser.tracks.database import TrackDatabase

        out = io.StringIO()
        shell = InteractiveShell(
            track_db=TrackDatabase(),
            formatters=build_formatters(),
            input_stream=io.StringIO(""),  # immediate EOF
            output_stream=out,
        )
        shell.run()
        assert "Exiting" in out.getvalue()

    # -- truncation --

    def test_long_callsign_truncated(self) -> None:
        track = Track(
            stn=100,
            callsign="VERYLONGCALLSIGN99",
            last_updated=datetime(2025, 1, 1, tzinfo=timezone.utc),
            message_count=1,
        )
        output = _run_shell(["list", "quit"], tracks=[track])
        assert "VERYLONGCAL~" in output
        assert "VERYLONGCALLSIGN99" not in output

    # -- export --

    def test_export_json_all_tracks(self, tmp_path: object) -> None:
        import json
        import pathlib
        filepath = pathlib.Path(str(tmp_path)) / "out.json"
        output = _run_shell(
            [f"export json {filepath}", "quit"],
            tracks=self._sample_tracks(),
        )
        assert "Exported 3 tracks" in output
        lines = filepath.read_text().strip().splitlines()
        assert len(lines) == 3
        parsed = json.loads(lines[0])
        assert "stn" in parsed

    def test_export_csv_with_header(self, tmp_path: object) -> None:
        import pathlib
        filepath = pathlib.Path(str(tmp_path)) / "out.csv"
        output = _run_shell(
            [f"export csv {filepath}", "quit"],
            tracks=self._sample_tracks(),
        )
        assert "Exported 3 tracks" in output
        lines = filepath.read_text().strip().splitlines()
        # Header + 3 data rows
        assert len(lines) == 4
        assert "stn" in lines[0].lower()

    def test_export_with_search_filter(self, tmp_path: object) -> None:
        import json
        import pathlib
        filepath = pathlib.Path(str(tmp_path)) / "hostile.json"
        output = _run_shell(
            [f"export json {filepath} hostile", "quit"],
            tracks=self._sample_tracks(),
        )
        assert "Exported 1 track" in output
        lines = filepath.read_text().strip().splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["identity"] == "HOSTILE"

    def test_export_no_args(self) -> None:
        output = _run_shell(["export", "quit"])
        assert "Usage: export" in output

    def test_export_bad_path(self) -> None:
        output = _run_shell(
            ["export json /nonexistent/dir/file.json", "quit"],
            tracks=self._sample_tracks(),
        )
        assert "Error writing" in output

    # -- config --

    def test_config_show(self) -> None:
        output = _run_shell(["config", "quit"])
        assert "format:" in output
        assert "TACREP" in output
        assert "originator:" in output
        assert "classification:" in output

    def test_config_originator(self) -> None:
        output = _run_shell(
            ["config originator CTF124", "tacrep 100", "quit"],
            tracks=self._sample_tracks(),
        )
        assert "originator set to: CTF124" in output
        assert "CTF124" in output

    def test_config_classification(self) -> None:
        output = _run_shell(
            ["config classification SECRET", "tacrep 100", "quit"],
            tracks=self._sample_tracks(),
        )
        assert "classification set to: SECRET" in output
        assert "SECRET" in output

    def test_config_unknown_key(self) -> None:
        output = _run_shell(["config bogus", "quit"])
        assert "Unknown config key" in output

    # -- debug --

    def test_debug_shows_history(self) -> None:
        output = _run_shell(["debug 100", "quit"], tracks=self._sample_tracks())
        assert "0o00144" in output  # octal STN for 100
        assert "Messages:" in output
        assert "J3.2" in output
        assert "Recent messages" in output

    def test_debug_no_track(self) -> None:
        output = _run_shell(["debug 99999", "quit"])
        assert "No track found" in output

    def test_debug_no_args(self) -> None:
        output = _run_shell(["debug", "quit"])
        assert "Usage: debug" in output

    # -- list with aging --

    def test_list_hides_dropped(self) -> None:
        """Default list should hide DROPPED tracks."""
        import io
        from link16_parser.cli.shell import InteractiveShell
        from link16_parser.output import build_formatters
        from link16_parser.tracks.database import TrackDatabase

        db = TrackDatabase(stale_ttl=60.0, drop_ttl=60.0)
        tracks = self._sample_tracks()
        for t in tracks:
            msg = Link16Message(
                stn=t.stn, msg_type="J3.2",
                timestamp=t.last_updated or datetime(2025, 1, 1, tzinfo=timezone.utc),
                callsign=t.callsign, identity=t.identity, platform=t.platform,
                position=t.position, fields=dict(t.fields) if t.fields else {},
            )
            db.update(msg)
        # Manually drop one track
        with db._lock:  # pyright: ignore[reportPrivateUsage]
            db._tracks[200].status = TrackStatus.DROPPED  # pyright: ignore[reportPrivateUsage]

        inp = io.StringIO("list\nquit\n")
        out = io.StringIO()
        shell = InteractiveShell(track_db=db, formatters=build_formatters(),
                                 input_stream=inp, output_stream=out)
        shell.run()
        output = out.getvalue()
        assert "VIPER01" in output
        assert "SNAKE11" not in output  # dropped, hidden

    def test_list_all_shows_dropped(self) -> None:
        """'list all' should include DROPPED tracks."""
        import io
        from link16_parser.cli.shell import InteractiveShell
        from link16_parser.output import build_formatters
        from link16_parser.tracks.database import TrackDatabase

        db = TrackDatabase(stale_ttl=60.0, drop_ttl=60.0)
        tracks = self._sample_tracks()
        for t in tracks:
            msg = Link16Message(
                stn=t.stn, msg_type="J3.2",
                timestamp=t.last_updated or datetime(2025, 1, 1, tzinfo=timezone.utc),
                callsign=t.callsign, identity=t.identity, platform=t.platform,
                position=t.position, fields=dict(t.fields) if t.fields else {},
            )
            db.update(msg)
        with db._lock:  # pyright: ignore[reportPrivateUsage]
            db._tracks[200].status = TrackStatus.DROPPED  # pyright: ignore[reportPrivateUsage]

        inp = io.StringIO("list all\nquit\n")
        out = io.StringIO()
        shell = InteractiveShell(track_db=db, formatters=build_formatters(),
                                 input_stream=inp, output_stream=out)
        shell.run()
        output = out.getvalue()
        assert "VIPER01" in output
        assert "SNAKE11" in output  # dropped but visible with 'all'

    def test_config_stale_ttl(self) -> None:
        output = _run_shell(["config stale-ttl 60", "config", "quit"])
        assert "stale-ttl set to: 60s" in output
        assert "stale-ttl:      60s" in output

    def test_config_drop_ttl(self) -> None:
        output = _run_shell(["config drop-ttl 180", "config", "quit"])
        assert "drop-ttl set to: 180s" in output
        assert "drop-ttl:       180s" in output
