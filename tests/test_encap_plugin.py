"""Tests for the JREAP-C encapsulation plugin loading system."""

from __future__ import annotations

import types
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import pytest

from link16_parser.core.types import RawJWord
from link16_parser.encapsulation import (
    DECODER_REGISTRY,
    build_decoder,
    load_encap_plugin,
    register_encap_plugin,
    resolve_encap_plugin,
)


# ---------------------------------------------------------------------------
# A fake plugin decoder for testing
# ---------------------------------------------------------------------------

class _FakeJreapCDecoder:
    """Fake JREAP-C decoder that returns a single dummy word."""

    @property
    def name(self) -> str:
        return "JREAP-C"

    def decode(self, _payload: bytes, pcap_timestamp: float) -> list[RawJWord]:
        return [RawJWord(
            data=b"\x00" * 10,
            stn=777,
            npg=0,
            timestamp=datetime.fromtimestamp(pcap_timestamp, tz=timezone.utc),
        )]


def _make_fake_module() -> types.ModuleType:
    """Create a fake module containing _FakeJreapCDecoder as JreapCDecoder."""
    mod = types.ModuleType("fake_jreap")
    mod.JreapCDecoder = _FakeJreapCDecoder  # type: ignore[attr-defined]
    return mod


def _make_empty_module() -> types.ModuleType:
    """Create a module with no JreapCDecoder class."""
    return types.ModuleType("empty_module")


# ---------------------------------------------------------------------------
# resolve_encap_plugin
# ---------------------------------------------------------------------------

class TestResolveEncapPlugin:
    def test_cli_arg_returned(self) -> None:
        assert resolve_encap_plugin("my.module") == "my.module"

    def test_env_var_returned(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LINK16_ENCAP_PLUGIN", "env.module")
        assert resolve_encap_plugin(None) == "env.module"

    def test_cli_arg_takes_precedence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LINK16_ENCAP_PLUGIN", "env.module")
        assert resolve_encap_plugin("cli.module") == "cli.module"

    def test_returns_none_when_nothing_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LINK16_ENCAP_PLUGIN", raising=False)
        assert resolve_encap_plugin(None) is None


# ---------------------------------------------------------------------------
# load_encap_plugin
# ---------------------------------------------------------------------------

class TestLoadEncapPlugin:
    def test_loads_valid_module(self) -> None:
        with patch("importlib.import_module", return_value=_make_fake_module()):
            cls = load_encap_plugin("fake_jreap")
        assert cls is _FakeJreapCDecoder

    def test_returns_none_on_import_error(self) -> None:
        with patch("importlib.import_module", side_effect=ModuleNotFoundError("nope")):
            cls = load_encap_plugin("bad.module")
        assert cls is None

    def test_returns_none_when_class_missing(self) -> None:
        with patch("importlib.import_module", return_value=_make_empty_module()):
            cls = load_encap_plugin("empty_module")
        assert cls is None

    def test_returns_none_when_instantiation_fails(self) -> None:
        class BadDecoder:
            def __init__(self) -> None:
                raise RuntimeError("boom")

        mod = types.ModuleType("bad_init")
        mod.JreapCDecoder = BadDecoder  # type: ignore[attr-defined]

        with patch("importlib.import_module", return_value=mod):
            cls = load_encap_plugin("bad_init")
        assert cls is None


# ---------------------------------------------------------------------------
# register_encap_plugin
# ---------------------------------------------------------------------------

class TestRegisterEncapPlugin:
    def _save_and_restore_registry(self) -> type[Any]:
        """Return the original jreap-c class for restoration."""
        return DECODER_REGISTRY["jreap-c"]

    def test_plugin_replaces_stub(self) -> None:
        original = self._save_and_restore_registry()
        try:
            with patch("importlib.import_module", return_value=_make_fake_module()):
                register_encap_plugin(cli_arg="fake_jreap")
            assert DECODER_REGISTRY["jreap-c"] is _FakeJreapCDecoder
        finally:
            DECODER_REGISTRY["jreap-c"] = original

    def test_import_failure_keeps_stub(self) -> None:
        original = self._save_and_restore_registry()
        try:
            with patch("importlib.import_module", side_effect=ModuleNotFoundError("nope")):
                register_encap_plugin(cli_arg="bad.module")
            assert DECODER_REGISTRY["jreap-c"] is original
        finally:
            DECODER_REGISTRY["jreap-c"] = original

    def test_no_plugin_configured_is_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LINK16_ENCAP_PLUGIN", raising=False)
        original = self._save_and_restore_registry()
        try:
            register_encap_plugin(cli_arg=None)
            assert DECODER_REGISTRY["jreap-c"] is original
        finally:
            DECODER_REGISTRY["jreap-c"] = original


# ---------------------------------------------------------------------------
# Integration: plugin wired through AutoDecoder
# ---------------------------------------------------------------------------

class TestPluginIntegration:
    def test_auto_decoder_uses_plugin(self) -> None:
        original = DECODER_REGISTRY["jreap-c"]
        try:
            with patch("importlib.import_module", return_value=_make_fake_module()):
                register_encap_plugin(cli_arg="fake_jreap")

            auto = build_decoder("auto")
            # Use a payload that won't match SIMPLE or SISO-J heuristics
            payload = b"\xFE\xED" + b"\x00" * 50
            words = auto.decode(payload, 1_700_000_000.0)

            assert len(words) == 1
            assert words[0].stn == 777
        finally:
            DECODER_REGISTRY["jreap-c"] = original
