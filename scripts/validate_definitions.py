#!/usr/bin/env python3
"""Validate JSON message definition files.

Checks that definition files are well-formed, internally consistent,
and free of common transcription mistakes. Intended for CI pipelines
and for humans checking their work after transcribing from the PDF.

Usage::

    python scripts/validate_definitions.py path/to/definitions/

Exit codes:
    0 — all definitions are valid.
    1 — one or more errors found (printed to stderr).
    2 — usage error (no directory argument, directory not found).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Allow running from the repo root without installing the package.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from link16_parser.link16.messages.schema import (  # noqa: E402
    validate_definition,
    validate_no_duplicate_keys,
)


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <definitions-directory>", file=sys.stderr)
        return 2

    defn_dir = Path(sys.argv[1])
    if not defn_dir.is_dir():
        print(f"Error: not a directory: {defn_dir}", file=sys.stderr)
        return 2

    json_files = sorted(defn_dir.glob("*.json"))
    if not json_files:
        print(f"No *.json files found in {defn_dir}")
        return 0

    all_errors: dict[str, list[str]] = {}
    loaded: list[tuple[str, dict[str, Any]]] = []

    for path in json_files:
        filepath = str(path)
        try:
            with open(path) as f:
                defn: dict[str, Any] = json.load(f)
        except json.JSONDecodeError as exc:
            all_errors[filepath] = [f"{filepath}: invalid JSON: {exc}"]
            continue
        except OSError as exc:
            all_errors[filepath] = [f"{filepath}: cannot read file: {exc}"]
            continue

        errors = validate_definition(defn, filepath=filepath)
        if errors:
            all_errors[filepath] = errors
        loaded.append((filepath, defn))

    # Cross-file duplicate check
    dup_errors = validate_no_duplicate_keys(loaded)
    if dup_errors:
        all_errors["<cross-file>"] = dup_errors

    if not all_errors:
        print(f"OK: {len(json_files)} definition(s) validated successfully.")
        return 0

    # Print errors grouped by file
    total = 0
    for filepath, errors in all_errors.items():
        print(f"\n{filepath}:", file=sys.stderr)
        for err in errors:
            # Strip filepath prefix if it's already in the error message
            msg = err[len(filepath) + 2:] if err.startswith(filepath + ": ") else err
            print(f"  - {msg}", file=sys.stderr)
            total += 1

    print(f"\n{total} error(s) in {len(all_errors)} file(s).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
