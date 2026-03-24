"""Load JSON message definitions and resolve the definitions directory.

Searches for definition files in order of precedence:

1. Explicit path from CLI ``--definitions-dir`` argument.
2. ``LINK16_DEFINITIONS`` environment variable.
3. Built-in ``link16_parser/link16/definitions/`` directory.

If no directory is found (or the directory is empty), returns an empty
list — the parser falls back to its hardcoded stub decoders.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from link16_parser.link16.messages.definition_decoder import DefinitionDecoder
from link16_parser.link16.messages.schema import (
    validate_definition,
    validate_no_duplicate_keys,
)

logger = logging.getLogger(__name__)

#: Built-in definitions directory (may be empty).
_BUILTIN_DIR = Path(__file__).resolve().parent.parent / "definitions"


def find_definitions_dir(cli_arg: str | None = None) -> Path | None:
    """Resolve the definitions directory from multiple sources.

    Args:
        cli_arg: Explicit path from the CLI (highest precedence).

    Returns:
        A ``Path`` to a directory containing ``*.json`` files, or
        ``None`` if no definitions are available.
    """
    candidates: list[Path] = []

    if cli_arg is not None:
        candidates.append(Path(cli_arg))

    env_val = os.environ.get("LINK16_DEFINITIONS")
    if env_val is not None:
        candidates.append(Path(env_val))

    candidates.append(_BUILTIN_DIR)

    for path in candidates:
        if path.is_dir() and any(path.glob("*.json")):
            return path

    return None


def load_definitions(definitions_dir: str | Path) -> list[DefinitionDecoder]:
    """Load all ``*.json`` definition files from a directory.

    Args:
        definitions_dir: Path to a directory containing JSON files.

    Returns:
        A list of ``DefinitionDecoder`` instances, one per valid file.

    Raises:
        ValueError: If any file fails validation or duplicates exist.
    """
    dirpath = Path(definitions_dir)
    json_files = sorted(dirpath.glob("*.json"))
    if not json_files:
        return []

    loaded: list[tuple[str, dict[str, Any]]] = []
    all_errors: list[str] = []

    for path in json_files:
        filepath = str(path)
        try:
            with open(path) as f:
                defn: dict[str, Any] = json.load(f)
        except json.JSONDecodeError as exc:
            all_errors.append(f"{filepath}: invalid JSON: {exc}")
            continue
        except OSError as exc:
            all_errors.append(f"{filepath}: cannot read file: {exc}")
            continue

        errors = validate_definition(defn, filepath=filepath)
        if errors:
            all_errors.extend(errors)
        else:
            loaded.append((filepath, defn))

    # Cross-file duplicate check
    dup_errors = validate_no_duplicate_keys(loaded)
    all_errors.extend(dup_errors)

    if all_errors:
        msg = "Message definition errors:\n" + "\n".join(f"  {e}" for e in all_errors)
        raise ValueError(msg)

    decoders: list[DefinitionDecoder] = []
    for filepath, defn in loaded:
        decoder = DefinitionDecoder(defn)
        logger.info(
            "Loaded data-driven decoder: %s (label=%d, sublabel=%d) from %s",
            decoder.msg_type_name, decoder.label, decoder.sublabel, filepath,
        )
        decoders.append(decoder)

    return decoders
