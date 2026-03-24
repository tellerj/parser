"""Encapsulation decoders — strip transport-layer wrappers to extract J-words.

Each decoder handles one wire format (SIMPLE, DIS/SISO-J, JREAP-C, etc.)
and satisfies the ``EncapsulationDecoder`` protocol defined in
``core/interfaces.py``.

How to add a new encapsulation format
=====================================

1. Create a new module in this package (e.g. ``my_format.py``).

2. Write a class with two members that match the ``EncapsulationDecoder``
   protocol::

       class MyFormatDecoder:
           @property
           def name(self) -> str:
               return "MY-FORMAT"

           def decode(self, payload: bytes, pcap_timestamp: float) -> list[RawJWord]:
               # Validate magic bytes / header.
               # Parse your format's header to extract NPG, STN, word count.
               # Slice out each 10-byte J-word.
               # Return a list of RawJWord objects (or [] if invalid).
               ...

   No base class or inheritance needed — just match the method signatures.

3. Register it in this file (``encapsulation/__init__.py``):

   a. Import your class.
   b. Add an entry to ``DECODER_REGISTRY``.
   c. If your format has a heuristic signature (magic bytes, PDU type),
      add a fast-path check in ``detect.py:AutoDecoder.decode()``.

4. Write a test in ``tests/`` that feeds known bytes through your decoder
   and asserts the correct ``RawJWord`` output.

Existing implementations
========================

- ``simple.py``  — STANAG 5602 / SIMPLE (fully documented, public).
- ``siso_j.py``  — DIS Signal PDU / SISO-STD-002 (fully documented, public).
- ``jreap_c.py`` — MIL-STD-3011 / JREAP-C (stub — awaiting spec access).
- ``detect.py``  — ``AutoDecoder`` heuristic dispatcher.

External plugin (JREAP-C)
=========================

The JREAP-C decoder can be injected from an external Python package::

    python -m link16_parser --file cap.pcap --encap-plugin jreap_decoder.decoder

Or via environment variable::

    export LINK16_ENCAP_PLUGIN=jreap_decoder.decoder

The module must contain a class named ``JreapCDecoder`` matching the
``EncapsulationDecoder`` protocol. See ``docs/jreap-c-plugin-guide.md``.
"""

from __future__ import annotations

import importlib
import logging
import os

from link16_parser.core.interfaces import EncapsulationDecoder
from link16_parser.encapsulation.detect import AutoDecoder
from link16_parser.encapsulation.jreap_c import JreapCDecoder
from link16_parser.encapsulation.simple import SimpleDecoder
from link16_parser.encapsulation.siso_j import SisoJDecoder

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Decoder registry — maps CLI-friendly name to decoder class.
# To add a new format: import it above and add an entry here.
# ---------------------------------------------------------------------------

DECODER_REGISTRY: dict[str, type[EncapsulationDecoder]] = {
    "simple": SimpleDecoder,
    "siso-j": SisoJDecoder,
    "jreap-c": JreapCDecoder,
}

ENCAP_CHOICES: list[str] = ["auto", *DECODER_REGISTRY]


def build_decoder(name: str) -> EncapsulationDecoder:
    """Instantiate the encapsulation decoder for the given format name.

    Args:
        name: One of ``ENCAP_CHOICES`` — ``"auto"``, ``"simple"``,
              ``"siso-j"``, ``"jreap-c"``.

    Returns:
        An ``EncapsulationDecoder`` instance.

    Raises:
        KeyError: If *name* is not in ``ENCAP_CHOICES``.
    """
    if name == "auto":
        concrete = [cls() for cls in DECODER_REGISTRY.values()]
        return AutoDecoder(decoders=concrete)
    return DECODER_REGISTRY[name]()


def resolve_encap_plugin(cli_arg: str | None = None) -> str | None:
    """Resolve plugin module path from CLI arg or environment variable.

    Args:
        cli_arg: Explicit module path from ``--encap-plugin`` (highest precedence).

    Returns:
        Dotted module path string, or ``None`` if no plugin configured.
    """
    if cli_arg is not None:
        return cli_arg
    return os.environ.get("LINK16_ENCAP_PLUGIN")


def load_encap_plugin(module_path: str) -> type[EncapsulationDecoder] | None:
    """Load a ``JreapCDecoder`` class from an external module.

    Args:
        module_path: Dotted Python module path (e.g. ``"jreap_decoder.decoder"``).

    Returns:
        The decoder class, or ``None`` if loading fails.
    """
    try:
        mod = importlib.import_module(module_path)
    except (ModuleNotFoundError, ImportError) as exc:
        logger.error("Cannot import encap plugin %r: %s", module_path, exc)
        return None

    cls = getattr(mod, "JreapCDecoder", None)
    if cls is None:
        logger.error("Module %r has no 'JreapCDecoder' class", module_path)
        return None

    # Smoke-test: instantiate and check protocol shape
    try:
        instance = cls()
        _ = instance.name
    except Exception as exc:
        logger.error("Failed to instantiate JreapCDecoder from %r: %s", module_path, exc)
        return None

    return cls  # type: ignore[no-any-return]


def register_encap_plugin(cli_arg: str | None = None) -> None:
    """Load and register an external JREAP-C plugin if configured.

    Replaces the stub ``JreapCDecoder`` in the decoder registry with the
    plugin class.  Falls back silently to the stub if no plugin is
    configured or if loading fails.

    Args:
        cli_arg: Explicit module path from ``--encap-plugin``.
    """
    module_path = resolve_encap_plugin(cli_arg)
    if module_path is None:
        return

    cls = load_encap_plugin(module_path)
    if cls is None:
        logger.warning("JREAP-C plugin failed to load; using stub")
        return

    DECODER_REGISTRY["jreap-c"] = cls
    logger.info("Loaded JREAP-C plugin from %s", module_path)


__all__ = [
    "build_decoder",
    "register_encap_plugin",
    "resolve_encap_plugin",
    "load_encap_plugin",
    "DECODER_REGISTRY",
    "ENCAP_CHOICES",
    "AutoDecoder",
    "SimpleDecoder",
    "SisoJDecoder",
    "JreapCDecoder",
]
