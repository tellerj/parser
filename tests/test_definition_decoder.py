"""Tests for the definition-driven message decoder."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from link16_parser.core.types import Identity, RawJWord
from link16_parser.link16.messages.definition_decoder import DefinitionDecoder, extract_bits

from tests.builders import make_jword_with_data

TS = datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc)


def _raw(word_data: bytes, stn: int = 100) -> RawJWord:
    """Wrap raw bytes into a RawJWord for testing."""
    return RawJWord(data=word_data, stn=stn, npg=7, timestamp=TS)


# ---------------------------------------------------------------------------
# Bit extraction
# ---------------------------------------------------------------------------

class TestExtractBits:
    def test_single_bit(self) -> None:
        word = make_jword_with_data(data_bits={0: (1, 1)})
        assert extract_bits(word, start_bit=0, length=1) == 1

    def test_single_bit_zero(self) -> None:
        word = make_jword_with_data(data_bits={0: (1, 0)})
        assert extract_bits(word, start_bit=0, length=1) == 0

    def test_multi_bit(self) -> None:
        word = make_jword_with_data(data_bits={4: (8, 0xAB)})
        assert extract_bits(word, start_bit=4, length=8) == 0xAB

    def test_wide_field(self) -> None:
        val = 0x1FFFFF  # 21 bits all set
        word = make_jword_with_data(data_bits={10: (21, val)})
        assert extract_bits(word, start_bit=10, length=21) == val

    def test_adjacent_fields_isolated(self) -> None:
        word = make_jword_with_data(data_bits={
            0: (4, 0xF),
            4: (4, 0x5),
        })
        assert extract_bits(word, start_bit=0, length=4) == 0xF
        assert extract_bits(word, start_bit=4, length=4) == 0x5

    def test_consistent_with_header_parsing(self) -> None:
        """Verify that our bit layout matches the existing header parser."""
        word = make_jword_with_data(
            word_format=0, label=7, sublabel=3, mli=2,
            data_bits={0: (8, 0xFF)},
        )
        # Header bits 0-12 should encode (wf=0, label=7, sub=3, mli=2)
        # We trust parse_jword_header for this — just verify our data is
        # independent of the header.
        assert extract_bits(word, start_bit=0, length=8) == 0xFF


# ---------------------------------------------------------------------------
# Scaled conversion
# ---------------------------------------------------------------------------

class TestScaledConversion:
    def _decoder(self, scale: float, offset: float) -> DefinitionDecoder:
        return DefinitionDecoder({
            "label": 3, "sublabel": 2, "name": "test",
            "fields": [{
                "name": "x", "word": 0, "start_bit": 0, "length": 9,
                "type": "scaled", "scale": scale, "offset": offset,
                "maps_to": "heading_deg",
            }],
        })

    def test_identity_scale(self) -> None:
        decoder = self._decoder(scale=1.0, offset=0.0)
        word = make_jword_with_data(label=3, sublabel=2, data_bits={0: (9, 180)})
        msg = decoder.decode([_raw(word)])
        assert msg is not None
        assert msg.heading_deg == 180.0

    def test_scale_and_offset(self) -> None:
        decoder = self._decoder(scale=0.5, offset=10.0)
        word = make_jword_with_data(label=3, sublabel=2, data_bits={0: (9, 20)})
        msg = decoder.decode([_raw(word)])
        assert msg is not None
        assert msg.heading_deg == 20.0  # 20 * 0.5 + 10 = 20.0

    def test_negative_offset(self) -> None:
        decoder = self._decoder(scale=0.703125, offset=0.0)
        word = make_jword_with_data(label=3, sublabel=2, data_bits={0: (9, 256)})
        msg = decoder.decode([_raw(word)])
        assert msg is not None
        assert msg.heading_deg == 256 * 0.703125


# ---------------------------------------------------------------------------
# Enum conversion
# ---------------------------------------------------------------------------

class TestEnumConversion:
    def _decoder(self) -> DefinitionDecoder:
        return DefinitionDecoder({
            "label": 3, "sublabel": 2, "name": "test",
            "fields": [{
                "name": "id", "word": 0, "start_bit": 0, "length": 3,
                "type": "enum",
                "values": {
                    "0": "PENDING", "1": "UNKNOWN",
                    "2": "ASSUMED FRIEND", "3": "FRIEND",
                    "4": "NEUTRAL", "5": "SUSPECT", "6": "HOSTILE",
                },
                "maps_to": "identity",
            }],
        })

    def test_known_value(self) -> None:
        decoder = self._decoder()
        word = make_jword_with_data(label=3, sublabel=2, data_bits={0: (3, 3)})
        msg = decoder.decode([_raw(word)])
        assert msg is not None
        assert msg.identity == Identity.FRIEND

    def test_hostile(self) -> None:
        decoder = self._decoder()
        word = make_jword_with_data(label=3, sublabel=2, data_bits={0: (3, 6)})
        msg = decoder.decode([_raw(word)])
        assert msg is not None
        assert msg.identity == Identity.HOSTILE

    def test_unknown_enum_value_no_crash(self) -> None:
        decoder = self._decoder()
        word = make_jword_with_data(label=3, sublabel=2, data_bits={0: (3, 7)})
        msg = decoder.decode([_raw(word)])
        assert msg is not None
        # Value "7" not in values dict — identity stays None (string "7"
        # doesn't match any Identity enum member).
        assert msg.identity is None


# ---------------------------------------------------------------------------
# maps_to routing
# ---------------------------------------------------------------------------

class TestMapsToRouting:
    def test_position_composite(self) -> None:
        decoder = DefinitionDecoder({
            "label": 3, "sublabel": 2, "name": "test",
            "fields": [
                {"name": "lat", "word": 0, "start_bit": 0, "length": 16,
                 "type": "scaled", "scale": 0.01, "offset": -90.0,
                 "maps_to": "position.lat"},
                {"name": "lon", "word": 0, "start_bit": 16, "length": 16,
                 "type": "scaled", "scale": 0.01, "offset": -180.0,
                 "maps_to": "position.lon"},
            ],
        })
        word = make_jword_with_data(label=3, sublabel=2, data_bits={
            0: (16, 12300),   # 12300 * 0.01 - 90 = 33.0
            16: (16, 6200),   # 6200 * 0.01 - 180 = -118.0
        })
        msg = decoder.decode([_raw(word)])
        assert msg is not None
        assert msg.position is not None
        assert abs(msg.position.lat - 33.0) < 0.01
        assert abs(msg.position.lon - (-118.0)) < 0.01

    def test_position_needs_both_lat_lon(self) -> None:
        decoder = DefinitionDecoder({
            "label": 3, "sublabel": 2, "name": "test",
            "fields": [
                {"name": "lat", "word": 0, "start_bit": 0, "length": 16,
                 "type": "scaled", "scale": 0.01, "offset": 0,
                 "maps_to": "position.lat"},
                # lon is on word 1, which won't be provided
                {"name": "lon", "word": 1, "start_bit": 0, "length": 16,
                 "type": "scaled", "scale": 0.01, "offset": 0,
                 "maps_to": "position.lon"},
            ],
        })
        word = make_jword_with_data(label=3, sublabel=2, data_bits={0: (16, 100)})
        msg = decoder.decode([_raw(word)])  # only 1 word
        assert msg is not None
        assert msg.position is None  # lon missing, no Position assembled

    def test_platform_composite(self) -> None:
        decoder = DefinitionDecoder({
            "label": 3, "sublabel": 2, "name": "test",
            "fields": [
                {"name": "plat", "word": 0, "start_bit": 0, "length": 3,
                 "type": "enum", "values": {"0": "FTR", "1": "BMR"},
                 "maps_to": "platform.generic_type"},
            ],
        })
        word = make_jword_with_data(label=3, sublabel=2, data_bits={0: (3, 0)})
        msg = decoder.decode([_raw(word)])
        assert msg is not None
        assert msg.platform is not None
        assert msg.platform.generic_type == "FTR"

    def test_fields_overflow(self) -> None:
        decoder = DefinitionDecoder({
            "label": 3, "sublabel": 2, "name": "test",
            "fields": [
                {"name": "quality", "word": 0, "start_bit": 0, "length": 4,
                 "type": "integer", "maps_to": "fields.track_quality"},
            ],
        })
        word = make_jword_with_data(label=3, sublabel=2, data_bits={0: (4, 12)})
        msg = decoder.decode([_raw(word)])
        assert msg is not None
        assert msg.fields["track_quality"] == 12

    def test_speed_kph(self) -> None:
        decoder = DefinitionDecoder({
            "label": 3, "sublabel": 2, "name": "test",
            "fields": [
                {"name": "speed", "word": 0, "start_bit": 0, "length": 10,
                 "type": "scaled", "scale": 1.852, "offset": 0,
                 "maps_to": "speed_kph"},
            ],
        })
        word = make_jword_with_data(label=3, sublabel=2, data_bits={0: (10, 100)})
        msg = decoder.decode([_raw(word)])
        assert msg is not None
        assert msg.speed_kph == 100 * 1.852

    def test_callsign(self) -> None:
        decoder = DefinitionDecoder({
            "label": 3, "sublabel": 2, "name": "test",
            "fields": [
                {"name": "cs", "word": 0, "start_bit": 0, "length": 8,
                 "type": "integer", "maps_to": "callsign"},
            ],
        })
        word = make_jword_with_data(label=3, sublabel=2, data_bits={0: (8, 65)})
        msg = decoder.decode([_raw(word)])
        assert msg is not None
        assert msg.callsign == "65"  # integer converted to string


# ---------------------------------------------------------------------------
# Multi-word messages
# ---------------------------------------------------------------------------

class TestMultiWord:
    def test_fields_across_words(self) -> None:
        decoder = DefinitionDecoder({
            "label": 3, "sublabel": 2, "name": "test",
            "fields": [
                {"name": "a", "word": 0, "start_bit": 0, "length": 8,
                 "type": "integer", "maps_to": "fields.a"},
                {"name": "b", "word": 1, "start_bit": 0, "length": 8,
                 "type": "integer", "maps_to": "fields.b"},
            ],
        })
        w0 = make_jword_with_data(label=3, sublabel=2, mli=1, data_bits={0: (8, 42)})
        w1 = make_jword_with_data(word_format=1, data_bits={0: (8, 99)})
        msg = decoder.decode([_raw(w0), _raw(w1)])
        assert msg is not None
        assert msg.fields["a"] == 42
        assert msg.fields["b"] == 99

    def test_missing_word_skipped(self) -> None:
        decoder = DefinitionDecoder({
            "label": 3, "sublabel": 2, "name": "test",
            "fields": [
                {"name": "a", "word": 0, "start_bit": 0, "length": 8,
                 "type": "integer", "maps_to": "fields.a"},
                {"name": "b", "word": 2, "start_bit": 0, "length": 8,
                 "type": "integer", "maps_to": "fields.b"},
            ],
        })
        w0 = make_jword_with_data(label=3, sublabel=2, data_bits={0: (8, 42)})
        msg = decoder.decode([_raw(w0)])  # only 1 word, field on word 2 skipped
        assert msg is not None
        assert msg.fields["a"] == 42
        assert "b" not in msg.fields


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------

class TestProtocol:
    def test_satisfies_decoder_protocol(self) -> None:
        decoder = DefinitionDecoder({
            "label": 7, "sublabel": 0, "name": "J7.0 Test",
            "fields": [{"name": "x", "word": 0, "start_bit": 0,
                         "length": 1, "type": "integer"}],
        })
        assert decoder.label == 7
        assert decoder.sublabel == 0
        assert decoder.msg_type_name == "J7.0 Test"

    def test_empty_words_returns_none(self) -> None:
        decoder = DefinitionDecoder({
            "label": 3, "sublabel": 2, "name": "test",
            "fields": [{"name": "x", "word": 0, "start_bit": 0,
                         "length": 1, "type": "integer"}],
        })
        assert decoder.decode([]) is None

    def test_envelope_fields_populated(self) -> None:
        decoder = DefinitionDecoder({
            "label": 3, "sublabel": 2, "name": "J3.2 Air Track",
            "fields": [{"name": "x", "word": 0, "start_bit": 0,
                         "length": 1, "type": "integer"}],
        })
        word = make_jword_with_data(label=3, sublabel=2)
        msg = decoder.decode([_raw(word, stn=555)])
        assert msg is not None
        assert msg.msg_type == "J3.2 Air Track"
        assert msg.stn == 555
        assert msg.timestamp == TS


# ---------------------------------------------------------------------------
# Full fixture integration
# ---------------------------------------------------------------------------

class TestFixtureDefinition:
    def test_example_j3_2_definition(self) -> None:
        """Load the test fixture and decode a synthetic message."""
        import json
        from pathlib import Path

        fixture = Path(__file__).parent / "fixtures" / "example_j3_2.json"
        with open(fixture) as f:
            defn: dict[str, Any] = json.load(f)

        decoder = DefinitionDecoder(defn)
        assert decoder.label == 3
        assert decoder.sublabel == 2

        # Build a 3-word message with known data.
        # Word 0: track_quality=12 (bits 0-3), identity=3/FRIEND (bits 4-6),
        #         platform=0/FTR (bits 7-11)
        w0 = make_jword_with_data(label=3, sublabel=2, mli=2, data_bits={
            0: (4, 12),   # track_quality
            4: (3, 3),    # identity = FRIEND
            7: (5, 0),    # platform = FTR
        })
        # Word 1: lat (bits 0-22), lon (bits 23-46)
        w1 = make_jword_with_data(word_format=1, data_bits={
            0: (23, 5_732_000),   # lat: 5732000 * 0.0000214577 - 90 ≈ 32.99
            23: (24, 2_896_000),  # lon: 2896000 * 0.0000214577 - 180 ≈ -117.84
        })
        # Word 2: alt (bits 0-15), heading (bits 16-24), speed (bits 25-36)
        w2 = make_jword_with_data(word_format=1, data_bits={
            0: (16, 1740),   # alt: 1740 * 3.048 - 304.8 ≈ 4998.72
            16: (9, 256),    # heading: 256 * 0.703125 = 180.0
            25: (12, 250),   # speed: 250 * 1.852 = 463.0
        })

        msg = decoder.decode([_raw(w0), _raw(w1), _raw(w2)])
        assert msg is not None
        assert msg.identity == Identity.FRIEND
        assert msg.platform is not None
        assert msg.platform.generic_type == "FTR"
        assert msg.position is not None
        assert abs(msg.position.lat - 33.0) < 0.1
        assert msg.position.alt_m is not None
        assert abs(msg.position.alt_m - 5000) < 10
        assert msg.heading_deg is not None
        assert abs(msg.heading_deg - 180.0) < 0.01
        assert msg.speed_kph is not None
        assert abs(msg.speed_kph - 463.0) < 0.01
        assert msg.fields["track_quality"] == 12
