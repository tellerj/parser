"""Tests for J-word header parsing, decoder routing, and MLI grouping."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from link16_parser.core.types import RawJWord, WordFormat
from link16_parser.link16.parser import JWordParser, parse_jword_header

from tests.builders import make_jword

TS = datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc)


def _raw(
    label: int = 2,
    sublabel: int = 2,
    mli: int = 0,
    word_format: int = 0,
    stn: int = 100,
) -> RawJWord:
    """Build a RawJWord with the given header fields."""
    return RawJWord(
        data=make_jword(word_format=word_format, label=label, sublabel=sublabel, mli=mli),
        stn=stn,
        npg=7,
        timestamp=TS,
    )


class TestParseJwordHeader:
    def test_j22(self) -> None:
        wf, label, sublabel, mli = parse_jword_header(_raw(label=2, sublabel=2, mli=0))
        assert wf == WordFormat.INITIAL
        assert label == 2
        assert sublabel == 2
        assert mli == 0

    def test_j32_with_mli(self) -> None:
        wf, label, sublabel, mli = parse_jword_header(_raw(label=3, sublabel=2, mli=2))
        assert wf == WordFormat.INITIAL
        assert label == 3
        assert sublabel == 2
        assert mli == 2

    def test_continuation(self) -> None:
        wf, _, _, _ = parse_jword_header(_raw(word_format=1))
        assert wf == WordFormat.CONTINUATION

    def test_extension(self) -> None:
        wf, _, _, _ = parse_jword_header(_raw(word_format=2))
        assert wf == WordFormat.EXTENSION


class TestJWordParser:
    def test_routes_to_correct_decoder(self, jword_parser: JWordParser) -> None:
        words = [
            _raw(label=2, sublabel=2),   # J2.2
            _raw(label=3, sublabel=2),   # J3.2
        ]
        messages = jword_parser.parse(words)

        assert len(messages) == 2
        assert messages[0].msg_type == "J2.2"
        assert messages[1].msg_type == "J3.2"

    def test_mli_groups_words(self, jword_parser: JWordParser) -> None:
        words = [
            _raw(label=2, sublabel=2, mli=1),         # initial, expects 1 continuation
            _raw(label=2, sublabel=2, word_format=1),  # continuation
        ]
        messages = jword_parser.parse(words)

        assert len(messages) == 1
        assert messages[0].fields["word_count"] == 2

    def test_skips_unregistered_labels(self, jword_parser: JWordParser) -> None:
        words = [_raw(label=15, sublabel=0)]
        messages = jword_parser.parse(words)

        assert messages == []

    def test_skips_orphaned_continuation(self, jword_parser: JWordParser) -> None:
        words = [_raw(word_format=1)]  # continuation with no preceding initial
        messages = jword_parser.parse(words)

        assert messages == []


# ---------------------------------------------------------------------------
# xfail stubs for MIL-STD-6016 field decoding
# ---------------------------------------------------------------------------

class TestMilStd6016Fields:
    """Placeholder tests that will pass once MIL-STD-6016 field decoding is implemented."""

    @pytest.mark.xfail(reason="awaiting MIL-STD-6016", strict=True)
    def test_j22_populates_position(self, jword_parser: JWordParser) -> None:
        messages = jword_parser.parse([_raw(label=2, sublabel=2)])
        assert messages[0].position is not None

    @pytest.mark.xfail(reason="awaiting MIL-STD-6016", strict=True)
    def test_j22_populates_callsign(self, jword_parser: JWordParser) -> None:
        messages = jword_parser.parse([_raw(label=2, sublabel=2)])
        assert messages[0].callsign is not None

    @pytest.mark.xfail(reason="awaiting MIL-STD-6016", strict=True)
    def test_j32_populates_identity(self, jword_parser: JWordParser) -> None:
        messages = jword_parser.parse([_raw(label=3, sublabel=2)])
        assert messages[0].identity is not None

    @pytest.mark.xfail(reason="awaiting MIL-STD-6016", strict=True)
    def test_j32_populates_platform(self, jword_parser: JWordParser) -> None:
        messages = jword_parser.parse([_raw(label=3, sublabel=2)])
        assert messages[0].platform is not None

    @pytest.mark.xfail(reason="awaiting MIL-STD-6016", strict=True)
    def test_j282_populates_text(self, jword_parser: JWordParser) -> None:
        messages = jword_parser.parse([_raw(label=28, sublabel=2)])
        assert "text" in messages[0].fields
