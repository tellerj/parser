"""Tests for JSON message definition schema validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from link16_parser.link16.messages.schema import (
    validate_definition,
    validate_no_duplicate_keys,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _minimal_defn(**overrides: Any) -> dict[str, Any]:
    """Build a minimal valid definition, applying overrides."""
    base: dict[str, Any] = {
        "label": 3,
        "sublabel": 2,
        "name": "J3.2 Air Track",
        "fields": [
            {
                "name": "heading",
                "word": 0,
                "start_bit": 0,
                "length": 9,
                "type": "scaled",
                "scale": 0.703125,
                "offset": 0,
                "maps_to": "heading_deg",
            },
        ],
    }
    base.update(overrides)
    return base


class TestValidDefinition:
    def test_fixture_file_is_valid(self) -> None:
        with open(FIXTURES / "example_j3_2.json") as f:
            defn: dict[str, Any] = json.load(f)
        assert validate_definition(defn) == []

    def test_minimal_valid(self) -> None:
        assert validate_definition(_minimal_defn()) == []


class TestMissingTopLevelKeys:
    def test_missing_label(self) -> None:
        defn = _minimal_defn()
        del defn["label"]
        errors = validate_definition(defn, filepath="test.json")
        assert any("missing required keys" in e for e in errors)

    def test_missing_fields(self) -> None:
        defn = _minimal_defn()
        del defn["fields"]
        errors = validate_definition(defn, filepath="test.json")
        assert any("missing required keys" in e for e in errors)


class TestTopLevelValueTypes:
    def test_label_out_of_range(self) -> None:
        errors = validate_definition(_minimal_defn(label=32))
        assert any("label" in e and "0-31" in e for e in errors)

    def test_sublabel_out_of_range(self) -> None:
        errors = validate_definition(_minimal_defn(sublabel=8))
        assert any("sublabel" in e and "0-7" in e for e in errors)

    def test_label_wrong_type(self) -> None:
        errors = validate_definition(_minimal_defn(label="three"))
        assert any("label" in e for e in errors)

    def test_empty_fields(self) -> None:
        errors = validate_definition(_minimal_defn(fields=[]))
        assert any("non-empty list" in e for e in errors)

    def test_empty_name(self) -> None:
        errors = validate_definition(_minimal_defn(name=""))
        assert any("non-empty string" in e for e in errors)


class TestFieldValidation:
    def test_missing_field_keys(self) -> None:
        defn = _minimal_defn(fields=[{"name": "x"}])
        errors = validate_definition(defn)
        assert any("missing required keys" in e for e in errors)

    def test_field_not_dict(self) -> None:
        defn = _minimal_defn(fields=["not a dict"])
        errors = validate_definition(defn)
        assert any("must be an object" in e for e in errors)

    def test_invalid_type(self) -> None:
        defn = _minimal_defn(fields=[{
            "name": "x", "word": 0, "start_bit": 0,
            "length": 8, "type": "bogus",
        }])
        errors = validate_definition(defn)
        assert any("'type' must be one of" in e for e in errors)

    def test_negative_word(self) -> None:
        defn = _minimal_defn(fields=[{
            "name": "x", "word": -1, "start_bit": 0,
            "length": 8, "type": "integer",
        }])
        errors = validate_definition(defn)
        assert any("non-negative integer" in e for e in errors)


class TestBitRangeChecks:
    def test_exceeds_57_bits(self) -> None:
        defn = _minimal_defn(fields=[{
            "name": "too_wide", "word": 0, "start_bit": 50,
            "length": 10, "type": "integer",
        }])
        errors = validate_definition(defn)
        assert any("exceeds" in e and "57" in e for e in errors)

    def test_overlapping_fields(self) -> None:
        defn = _minimal_defn(fields=[
            {"name": "a", "word": 0, "start_bit": 0, "length": 10, "type": "integer"},
            {"name": "b", "word": 0, "start_bit": 5, "length": 10, "type": "integer"},
        ])
        errors = validate_definition(defn)
        assert any("overlapping" in e for e in errors)

    def test_adjacent_fields_ok(self) -> None:
        defn = _minimal_defn(fields=[
            {"name": "a", "word": 0, "start_bit": 0, "length": 10, "type": "integer"},
            {"name": "b", "word": 0, "start_bit": 10, "length": 10, "type": "integer"},
        ])
        assert validate_definition(defn) == []

    def test_different_words_no_overlap(self) -> None:
        defn = _minimal_defn(fields=[
            {"name": "a", "word": 0, "start_bit": 0, "length": 10, "type": "integer"},
            {"name": "b", "word": 1, "start_bit": 0, "length": 10, "type": "integer"},
        ])
        assert validate_definition(defn) == []


class TestScaledFieldChecks:
    def test_missing_scale(self) -> None:
        defn = _minimal_defn(fields=[{
            "name": "x", "word": 0, "start_bit": 0, "length": 9,
            "type": "scaled", "offset": 0,
        }])
        errors = validate_definition(defn)
        assert any("'scale'" in e for e in errors)

    def test_missing_offset(self) -> None:
        defn = _minimal_defn(fields=[{
            "name": "x", "word": 0, "start_bit": 0, "length": 9,
            "type": "scaled", "scale": 1.0,
        }])
        errors = validate_definition(defn)
        assert any("'offset'" in e for e in errors)

    def test_non_numeric_scale(self) -> None:
        defn = _minimal_defn(fields=[{
            "name": "x", "word": 0, "start_bit": 0, "length": 9,
            "type": "scaled", "scale": "fast", "offset": 0,
        }])
        errors = validate_definition(defn)
        assert any("'scale'" in e for e in errors)


class TestEnumFieldChecks:
    def test_missing_values(self) -> None:
        defn = _minimal_defn(fields=[{
            "name": "x", "word": 0, "start_bit": 0, "length": 3,
            "type": "enum",
        }])
        errors = validate_definition(defn)
        assert any("'values'" in e for e in errors)

    def test_non_integer_keys(self) -> None:
        defn = _minimal_defn(fields=[{
            "name": "x", "word": 0, "start_bit": 0, "length": 3,
            "type": "enum", "values": {"abc": "FOO"},
        }])
        errors = validate_definition(defn)
        assert any("integer-coercible" in e for e in errors)

    def test_valid_string_integer_keys(self) -> None:
        defn = _minimal_defn(fields=[{
            "name": "x", "word": 0, "start_bit": 0, "length": 3,
            "type": "enum", "values": {"0": "FOO", "1": "BAR"},
        }])
        assert validate_definition(defn) == []


class TestMapsToValidation:
    def test_valid_direct(self) -> None:
        defn = _minimal_defn(fields=[{
            "name": "x", "word": 0, "start_bit": 0, "length": 9,
            "type": "scaled", "scale": 1.0, "offset": 0,
            "maps_to": "heading_deg",
        }])
        assert validate_definition(defn) == []

    def test_valid_position(self) -> None:
        defn = _minimal_defn(fields=[{
            "name": "x", "word": 0, "start_bit": 0, "length": 23,
            "type": "scaled", "scale": 1.0, "offset": 0,
            "maps_to": "position.lat",
        }])
        assert validate_definition(defn) == []

    def test_valid_fields_overflow(self) -> None:
        defn = _minimal_defn(fields=[{
            "name": "x", "word": 0, "start_bit": 0, "length": 8,
            "type": "integer", "maps_to": "fields.custom_thing",
        }])
        assert validate_definition(defn) == []

    def test_invalid_target(self) -> None:
        defn = _minimal_defn(fields=[{
            "name": "x", "word": 0, "start_bit": 0, "length": 9,
            "type": "scaled", "scale": 1.0, "offset": 0,
            "maps_to": "heading-deg",
        }])
        errors = validate_definition(defn)
        assert any("invalid 'maps_to'" in e for e in errors)

    def test_invalid_position_subfield(self) -> None:
        defn = _minimal_defn(fields=[{
            "name": "x", "word": 0, "start_bit": 0, "length": 9,
            "type": "scaled", "scale": 1.0, "offset": 0,
            "maps_to": "position.altitude",
        }])
        errors = validate_definition(defn)
        assert any("invalid 'maps_to'" in e for e in errors)

    def test_no_maps_to_is_ok(self) -> None:
        defn = _minimal_defn(fields=[{
            "name": "x", "word": 0, "start_bit": 0, "length": 8,
            "type": "integer",
        }])
        assert validate_definition(defn) == []


class TestDuplicateKeys:
    def test_no_duplicates(self) -> None:
        defs: list[tuple[str, dict[str, Any]]] = [
            ("a.json", {"label": 2, "sublabel": 2}),
            ("b.json", {"label": 3, "sublabel": 2}),
        ]
        assert validate_no_duplicate_keys(defs) == []

    def test_duplicate_detected(self) -> None:
        defs: list[tuple[str, dict[str, Any]]] = [
            ("a.json", {"label": 3, "sublabel": 2}),
            ("b.json", {"label": 3, "sublabel": 2}),
        ]
        errors = validate_no_duplicate_keys(defs)
        assert len(errors) == 1
        assert "duplicate" in errors[0]
