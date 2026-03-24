"""Tests for the JSON definition loader and directory resolution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from link16_parser.link16.messages.loader import (
    find_definitions_dir,
    load_definitions,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _write_defn(tmp_path: Path, filename: str, defn: dict[str, Any]) -> Path:
    """Write a JSON definition to a temp directory."""
    path = tmp_path / filename
    path.write_text(json.dumps(defn))
    return path


def _valid_defn(label: int = 3, sublabel: int = 2) -> dict[str, Any]:
    return {
        "label": label,
        "sublabel": sublabel,
        "name": f"J{label}.{sublabel} Test",
        "fields": [{
            "name": "x", "word": 0, "start_bit": 0,
            "length": 8, "type": "integer",
        }],
    }


# ---------------------------------------------------------------------------
# load_definitions
# ---------------------------------------------------------------------------

class TestLoadDefinitions:
    def test_loads_valid_directory(self, tmp_path: Path) -> None:
        _write_defn(tmp_path, "j3_2.json", _valid_defn(3, 2))
        _write_defn(tmp_path, "j2_2.json", _valid_defn(2, 2))

        decoders = load_definitions(tmp_path)
        assert len(decoders) == 2

        labels = {(d.label, d.sublabel) for d in decoders}
        assert (3, 2) in labels
        assert (2, 2) in labels

    def test_empty_directory(self, tmp_path: Path) -> None:
        decoders = load_definitions(tmp_path)
        assert decoders == []

    def test_malformed_json_raises(self, tmp_path: Path) -> None:
        (tmp_path / "bad.json").write_text("{not valid json")
        with pytest.raises(ValueError, match="invalid JSON"):
            load_definitions(tmp_path)

    def test_invalid_definition_raises(self, tmp_path: Path) -> None:
        _write_defn(tmp_path, "bad.json", {"label": 99})  # missing keys, bad label
        with pytest.raises(ValueError, match="definition errors"):
            load_definitions(tmp_path)

    def test_duplicate_label_sublabel_raises(self, tmp_path: Path) -> None:
        _write_defn(tmp_path, "a.json", _valid_defn(3, 2))
        _write_defn(tmp_path, "b.json", _valid_defn(3, 2))
        with pytest.raises(ValueError, match="duplicate"):
            load_definitions(tmp_path)

    def test_loads_fixture(self) -> None:
        decoders = load_definitions(FIXTURES)
        assert len(decoders) >= 1
        assert any(d.label == 3 and d.sublabel == 2 for d in decoders)


# ---------------------------------------------------------------------------
# find_definitions_dir
# ---------------------------------------------------------------------------

class TestFindDefinitionsDir:
    def test_cli_arg_takes_precedence(self, tmp_path: Path) -> None:
        _write_defn(tmp_path, "x.json", _valid_defn())
        result = find_definitions_dir(cli_arg=str(tmp_path))
        assert result == tmp_path

    def test_env_var_used(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_defn(tmp_path, "x.json", _valid_defn())
        monkeypatch.setenv("LINK16_DEFINITIONS", str(tmp_path))
        result = find_definitions_dir()
        assert result == tmp_path

    def test_cli_arg_over_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cli_dir = tmp_path / "cli"
        env_dir = tmp_path / "env"
        cli_dir.mkdir()
        env_dir.mkdir()
        _write_defn(cli_dir, "x.json", _valid_defn())
        _write_defn(env_dir, "x.json", _valid_defn())
        monkeypatch.setenv("LINK16_DEFINITIONS", str(env_dir))

        result = find_definitions_dir(cli_arg=str(cli_dir))
        assert result == cli_dir

    def test_returns_none_when_empty(self, tmp_path: Path) -> None:
        # tmp_path exists but has no JSON files
        result = find_definitions_dir(cli_arg=str(tmp_path))
        assert result is None

    def test_returns_none_when_nothing_configured(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("LINK16_DEFINITIONS", raising=False)
        # builtin dir exists but is empty (has only .gitkeep)
        result = find_definitions_dir()
        assert result is None
