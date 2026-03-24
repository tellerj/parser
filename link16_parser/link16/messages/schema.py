"""JSON message definition schema validation.

Validates that JSON definition files are well-formed and internally
consistent before they reach the decoder at runtime. Designed to catch
the kinds of mistakes a human makes when transcribing bit-field layouts
from a PDF: typos in field names, off-by-one bit ranges, missing
required keys, wrong types.

Usage::

    import json
    from link16_parser.link16.messages.schema import validate_definition

    with open("j3_2.json") as f:
        defn = json.load(f)

    errors = validate_definition(defn, filepath="j3_2.json")
    if errors:
        for e in errors:
            print(e)
"""

from __future__ import annotations

from typing import Any, cast

# ---------------------------------------------------------------------------
# Constants — the set of valid values for each constrained field
# ---------------------------------------------------------------------------

#: Field types recognised by DefinitionDecoder.
VALID_FIELD_TYPES = frozenset({
    "integer",
    "scaled",
    "enum",
    "string",
    "track_num",
    "flags",
})

#: Direct attributes on Link16Message that ``maps_to`` can target.
VALID_MAPS_TO_DIRECT = frozenset({
    "identity",
    "callsign",
    "heading_deg",
    "speed_kph",
    "track_number",
})

#: Dotted prefixes for composite ``maps_to`` targets.
#: ``position.lat``, ``platform.generic_type``, ``fields.custom_key``, etc.
VALID_MAPS_TO_PREFIXES = (
    "position.",
    "platform.",
    "fields.",
)

#: Valid sub-fields for each composite prefix.
_VALID_POSITION_SUBFIELDS = frozenset({"lat", "lon", "alt_m"})
_VALID_PLATFORM_SUBFIELDS = frozenset({"generic_type", "specific_type", "nationality"})

#: Maximum number of data bits in the FWF portion of a J-word.
#: Bits 13-69 of the 80-bit word = 57 bits.
MAX_DATA_BITS = 57

#: Required top-level keys in a definition.
REQUIRED_TOP_KEYS = frozenset({"label", "sublabel", "name", "fields"})

#: Required keys in each field entry.
REQUIRED_FIELD_KEYS = frozenset({"name", "word", "start_bit", "length", "type"})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_definition(
    defn: dict[str, Any],
    filepath: str = "<unknown>",
) -> list[str]:
    """Validate a single parsed JSON message definition.

    Args:
        defn: The parsed JSON dict (from ``json.load``).
        filepath: File path for error messages.

    Returns:
        A list of human-readable error strings. Empty means valid.
    """
    errors: list[str] = []

    # --- Top-level structure ---
    _check_top_level(defn, filepath, errors)
    if errors:
        # Can't validate fields if the structure is broken
        return errors

    # --- Field-level checks ---
    fields: list[Any] = defn["fields"]
    for i, field in enumerate(fields):
        _check_field(field, i, filepath, errors)

    # --- Cross-field: overlapping bit ranges within the same word ---
    _check_bit_overlaps(fields, filepath, errors)

    return errors


def validate_no_duplicate_keys(
    definitions: list[tuple[str, dict[str, Any]]],
) -> list[str]:
    """Check that no two definitions share the same (label, sublabel).

    Args:
        definitions: List of ``(filepath, parsed_dict)`` pairs.

    Returns:
        A list of human-readable error strings. Empty means no duplicates.
    """
    errors: list[str] = []
    seen: dict[tuple[int, int], str] = {}
    for filepath, defn in definitions:
        label = defn.get("label")
        sublabel = defn.get("sublabel")
        if not isinstance(label, int) or not isinstance(sublabel, int):
            continue  # Already caught by validate_definition
        key = (label, sublabel)
        if key in seen:
            errors.append(
                f"{filepath}: duplicate (label={label}, sublabel={sublabel}), "
                f"already defined in {seen[key]}"
            )
        else:
            seen[key] = filepath
    return errors


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_top_level(
    defn: dict[str, Any],
    filepath: str,
    errors: list[str],
) -> None:
    """Validate top-level keys and types."""
    missing = REQUIRED_TOP_KEYS - defn.keys()
    if missing:
        errors.append(f"{filepath}: missing required keys: {sorted(missing)}")
        return

    label: Any = defn["label"]
    sublabel: Any = defn["sublabel"]
    name: Any = defn["name"]
    fields: Any = defn["fields"]

    if not isinstance(label, int) or not (0 <= label <= 31):
        errors.append(f"{filepath}: 'label' must be an integer 0-31, got {label!r}")

    if not isinstance(sublabel, int) or not (0 <= sublabel <= 7):
        errors.append(f"{filepath}: 'sublabel' must be an integer 0-7, got {sublabel!r}")

    if not isinstance(name, str) or not name:
        errors.append(f"{filepath}: 'name' must be a non-empty string")

    if not isinstance(fields, list) or len(cast(list[Any], fields)) == 0:
        errors.append(f"{filepath}: 'fields' must be a non-empty list")


def _check_field(
    field: Any,
    index: int,
    filepath: str,
    errors: list[str],
) -> None:
    """Validate a single field entry."""
    if not isinstance(field, dict):
        errors.append(f"{filepath}: fields[{index}] must be an object, got {type(field).__name__}")
        return

    fld: dict[str, Any] = cast(dict[str, Any], field)
    prefix = f"{filepath}: fields[{index}]"

    # Required keys
    missing = REQUIRED_FIELD_KEYS - fld.keys()
    if missing:
        errors.append(f"{prefix}: missing required keys: {sorted(missing)}")
        return

    name: str | Any = fld["name"]
    word: int | Any = fld["word"]
    start_bit: int | Any = fld["start_bit"]
    length: int | Any = fld["length"]
    ftype: str | Any = fld["type"]

    # Type checks on required fields
    if not isinstance(name, str) or not name:
        errors.append(f"{prefix}: 'name' must be a non-empty string")

    if not isinstance(word, int) or word < 0:
        errors.append(f"{prefix} ({name}): 'word' must be a non-negative integer, got {word!r}")

    if not isinstance(start_bit, int) or start_bit < 0:
        errors.append(f"{prefix} ({name}): 'start_bit' must be a non-negative integer, got {start_bit!r}")

    if not isinstance(length, int) or length < 1:
        errors.append(f"{prefix} ({name}): 'length' must be a positive integer, got {length!r}")

    if not isinstance(ftype, str) or ftype not in VALID_FIELD_TYPES:
        errors.append(
            f"{prefix} ({name}): 'type' must be one of {sorted(VALID_FIELD_TYPES)}, got {ftype!r}"
        )

    # Bit range check
    if isinstance(start_bit, int) and isinstance(length, int):
        if start_bit + length > MAX_DATA_BITS:
            errors.append(
                f"{prefix} ({name}): start_bit ({start_bit}) + length ({length}) = "
                f"{start_bit + length} exceeds {MAX_DATA_BITS}-bit FWF data limit"
            )

    # Type-specific checks
    if ftype == "scaled":
        scale_val: Any = fld.get("scale")
        offset_val: Any = fld.get("offset")
        if "scale" not in fld or not isinstance(scale_val, (int, float)):
            errors.append(f"{prefix} ({name}): 'scaled' type requires numeric 'scale'")
        if "offset" not in fld or not isinstance(offset_val, (int, float)):
            errors.append(f"{prefix} ({name}): 'scaled' type requires numeric 'offset'")

    if ftype == "enum":
        values: Any = fld.get("values")
        if not isinstance(values, dict):
            errors.append(f"{prefix} ({name}): 'enum' type requires non-empty 'values' dict")
        else:
            values_dict: dict[str, Any] = cast(dict[str, Any], values)
            if len(values_dict) == 0:
                errors.append(f"{prefix} ({name}): 'enum' type requires non-empty 'values' dict")
            elif not all(_is_int_coercible(str(k)) for k in values_dict):
                errors.append(f"{prefix} ({name}): 'values' keys must be integer-coercible strings")

    # maps_to validation (optional key, but checked if present)
    maps_to: Any = fld.get("maps_to")
    if maps_to is not None:
        if not isinstance(maps_to, str) or not maps_to:
            errors.append(f"{prefix} ({name}): 'maps_to' must be a non-empty string")
        elif not _is_valid_maps_to(maps_to):
            errors.append(
                f"{prefix} ({name}): invalid 'maps_to' target {maps_to!r}. "
                f"Valid targets: {sorted(VALID_MAPS_TO_DIRECT)}, "
                f"or prefixed with: {', '.join(VALID_MAPS_TO_PREFIXES)}"
            )


def _check_bit_overlaps(
    fields: list[Any],
    filepath: str,
    errors: list[str],
) -> None:
    """Detect overlapping bit ranges within the same word index."""
    # Group fields by word index
    by_word: dict[int, list[tuple[str, int, int]]] = {}
    for raw_field in fields:
        if not isinstance(raw_field, dict):
            continue
        fld: dict[str, Any] = cast(dict[str, Any], raw_field)
        word: Any = fld.get("word")
        start: Any = fld.get("start_bit")
        length: Any = fld.get("length")
        name: str = fld.get("name", "?")
        if isinstance(word, int) and isinstance(start, int) and isinstance(length, int):
            by_word.setdefault(word, []).append((name, start, start + length))

    for _word_idx, ranges in by_word.items():
        # Sort by start bit
        ranges.sort(key=lambda r: r[1])
        for i in range(len(ranges) - 1):
            name_a, _, end_a = ranges[i]
            name_b, start_b, _ = ranges[i + 1]
            if end_a > start_b:
                errors.append(
                    f"{filepath}: word {_word_idx}: fields '{name_a}' and "
                    f"'{name_b}' have overlapping bit ranges"
                )


def _is_valid_maps_to(target: str) -> bool:
    """Check whether a maps_to target is valid."""
    if target in VALID_MAPS_TO_DIRECT:
        return True
    for prefix in VALID_MAPS_TO_PREFIXES:
        if target.startswith(prefix):
            suffix = target[len(prefix):]
            if not suffix:
                return False
            # Validate known sub-fields for position and platform
            if prefix == "position.":
                return suffix in _VALID_POSITION_SUBFIELDS
            if prefix == "platform.":
                return suffix in _VALID_PLATFORM_SUBFIELDS
            # fields.* accepts anything
            return True
    return False


def _is_int_coercible(value: str) -> bool:
    """Check if a string value can be interpreted as an integer."""
    try:
        int(value)
        return True
    except (ValueError, TypeError):
        return False
