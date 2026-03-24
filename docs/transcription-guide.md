# Message Definition Transcription Guide

This guide walks you through creating a JSON message definition file from the MIL-STD-6016 PDF. Each file defines one message type (e.g., J3.2 Air Track). No programming knowledge is required.

## What you need

- The MIL-STD-6016 PDF, open to the message type you're transcribing
- A text editor (VS Code, Notepad++, etc.)
- The validation tool (instructions at the end)

## Quick overview

A Link 16 message is made of one or more **J-words**. Each J-word is 80 bits:

```
[ 13-bit header | 57-bit data | 5-bit parity | 5-bit pad ]
```

You are transcribing the fields within the **57-bit data** portion. The header, parity, and padding are handled automatically — ignore them.

## Step 1: Identify the message

Find the message type in the PDF. Note three things:

- **Label** — the number before the dot (J**3**.2 → label `3`)
- **Sublabel** — the number after the dot (J3.**2** → sublabel `2`)
- **Name** — the full name (e.g., "J3.2 Air Track")

Create a new file named after the message type, e.g., `j3_2.json`, and start with:

```json
{
  "label": 3,
  "sublabel": 2,
  "name": "J3.2 Air Track",
  "fields": [
  ]
}
```

## Step 2: Read the bit-field table

The PDF shows a table of fields for each message. Each row tells you:

| PDF column | What it means |
|---|---|
| Field name | A human name like "Track Quality" or "Latitude" |
| Word | Which word: "Initial" = word 0, "C1" (first continuation) = word 1, "C2" = word 2, etc. |
| Bit position | Where the field starts and how wide it is, within the 57-bit data portion |
| Data type / encoding | How to interpret the raw bits |

## Step 3: Transcribe each field

For each row in the PDF table, add an entry to the `"fields"` array.

### Required keys for every field

```json
{
  "name": "track_quality",
  "word": 0,
  "start_bit": 0,
  "length": 4,
  "type": "integer"
}
```

| Key | How to fill it in |
|---|---|
| `name` | A short, descriptive name. Use lowercase with underscores. Your choice — it's just for readability. |
| `word` | `0` for the Initial word, `1` for C1, `2` for C2, etc. |
| `start_bit` | Bit position within the 57-bit data portion. **Bit 0 is the first data bit.** If the PDF numbers bits from the start of the full 80-bit word, subtract 13. |
| `length` | Number of bits. If the PDF says "bits 4-6", that's 3 bits. |
| `type` | See the type guide below. |

### Bit numbering — the most common mistake

The 57-bit data portion starts at bit 13 of the full word. In our JSON files, **`start_bit` is relative to the data portion, not the full word**.

- If the PDF says a field is at bits 13-16 of the word → `"start_bit": 0, "length": 4`
- If the PDF says bits 20-28 → `"start_bit": 7, "length": 9`
- General rule: `start_bit = pdf_bit_position - 13`

Some editions of the PDF number fields within the data portion already (starting from 0). In that case, use the numbers directly.

**Check which convention your PDF uses before starting.** Look at the first field — if it starts at bit 0, use the numbers as-is. If it starts at bit 13, subtract 13 from everything.

## Step 4: Choose the right type

### `integer` — raw numeric value

Use when the field is just a number with no conversion needed.

```json
{
  "name": "track_quality",
  "word": 0, "start_bit": 0, "length": 4,
  "type": "integer",
  "maps_to": "fields.track_quality"
}
```

### `scaled` — value with a formula

Use when the PDF gives a resolution or conversion factor. Common for lat, lon, altitude, heading, speed.

The formula is: **`output = raw_value × scale + offset`**

```json
{
  "name": "latitude",
  "word": 1, "start_bit": 0, "length": 23,
  "type": "scaled",
  "scale": 0.0000214577,
  "offset": -90.0,
  "maps_to": "position.lat"
}
```

**How to find `scale` and `offset`:**

The PDF usually states something like:
- "Resolution: 0.703125 degrees/LSB" → `"scale": 0.703125, "offset": 0`
- "Range: -90 to +90, 23-bit unsigned" → `"scale"` = 180 / (2^23 - 1), `"offset"` = -90.0
- "Range: 0 to 360 degrees, 9-bit" → `"scale"` = 360 / 512, `"offset"` = 0

If the PDF gives a range [min, max] with N bits:
- `scale` = (max - min) / (2^N - 1)
- `offset` = min

Both `scale` and `offset` are **required** for the `scaled` type. If there's no offset, use `0`.

### `enum` — coded value with named meanings

Use when the PDF lists a table of codes (e.g., 0 = Pending, 1 = Unknown, ...).

```json
{
  "name": "identity",
  "word": 0, "start_bit": 4, "length": 3,
  "type": "enum",
  "values": {
    "0": "PENDING",
    "1": "UNKNOWN",
    "2": "ASSUMED FRIEND",
    "3": "FRIEND",
    "4": "NEUTRAL",
    "5": "SUSPECT",
    "6": "HOSTILE"
  },
  "maps_to": "identity"
}
```

**Important:** The keys in `"values"` must be **strings** (with quotes), even though they represent numbers. Copy every code from the PDF table. If a code is listed as "Reserved" or "Spare", you can omit it.

### `string` — Link 16 character data

Use for fields that encode text using the Link 16 6-bit character set.

```json
{
  "name": "callsign",
  "word": 0, "start_bit": 10, "length": 48,
  "type": "string",
  "maps_to": "callsign"
}
```

### `track_num` — track number

Use for the 5-character alphanumeric track number encoding.

```json
{
  "name": "track_number",
  "word": 0, "start_bit": 0, "length": 25,
  "type": "track_num",
  "maps_to": "track_number"
}
```

### `flags` — raw bit flags

Use when the field is a set of bit flags that don't need individual decoding. The raw integer value is stored as-is.

```json
{
  "name": "status_flags",
  "word": 0, "start_bit": 12, "length": 6,
  "type": "flags",
  "maps_to": "fields.status_flags"
}
```

## Step 5: Set `maps_to`

The `maps_to` key tells the parser where to put the decoded value on the output message. It's optional — if omitted, the field is decoded but not mapped anywhere.

| Target | Use for |
|---|---|
| `identity` | Friend/hostile/neutral identification |
| `heading_deg` | Heading in degrees |
| `speed_kph` | Speed in km/h |
| `callsign` | Platform callsign |
| `track_number` | Track number |
| `position.lat` | Latitude (needs `position.lon` too) |
| `position.lon` | Longitude (needs `position.lat` too) |
| `position.alt_m` | Altitude in metres |
| `platform.generic_type` | Platform type (e.g., "FTR", "BMR") |
| `platform.specific_type` | Specific platform type |
| `platform.nationality` | Platform nationality |
| `fields.xxx` | Anything else — replace `xxx` with a descriptive name |

**Position requires both `lat` and `lon`** to appear in the same message. If only one is present, the position is dropped. `alt_m` is optional.

## Step 6: Validate

Save your file and run the validation tool:

```bash
python3 scripts/validate_definitions.py /path/to/your/definitions/
```

It checks for:
- Missing or misspelled keys
- Bit ranges that exceed 57 bits
- Overlapping fields within the same word
- Missing `scale`/`offset` on `scaled` fields
- Missing `values` on `enum` fields
- Invalid `maps_to` targets
- Duplicate message types across files

Fix any errors it reports and re-run until it passes.

## Rules and constraints

1. **One file per message type.** File naming is up to you, but `j3_2.json` is a sensible convention.
2. **Fields cannot span word boundaries.** If a logical value is split across two words in the PDF, create two separate fields (one per word) and map them both to `fields.xxx`. The parser handles each word independently.
3. **`start_bit + length` must not exceed 57.** The data portion is 57 bits (bits 13-69 of the 80-bit word). If your field exceeds this, double-check your bit numbering.
4. **No two fields in the same word can overlap.** The validator catches this.
5. **Enum keys are strings.** Write `"3": "FRIEND"`, not `3: "FRIEND"`.

## Complete example

Here is a full (fabricated) definition for a J3.2 Air Track message:

```json
{
  "label": 3,
  "sublabel": 2,
  "name": "J3.2 Air Track",
  "fields": [
    {
      "name": "track_quality",
      "word": 0,
      "start_bit": 0,
      "length": 4,
      "type": "integer",
      "maps_to": "fields.track_quality"
    },
    {
      "name": "identity",
      "word": 0,
      "start_bit": 4,
      "length": 3,
      "type": "enum",
      "values": {
        "0": "PENDING",
        "1": "UNKNOWN",
        "2": "ASSUMED FRIEND",
        "3": "FRIEND",
        "4": "NEUTRAL",
        "5": "SUSPECT",
        "6": "HOSTILE"
      },
      "maps_to": "identity"
    },
    {
      "name": "latitude",
      "word": 1,
      "start_bit": 0,
      "length": 23,
      "type": "scaled",
      "scale": 0.0000214577,
      "offset": -90.0,
      "maps_to": "position.lat"
    },
    {
      "name": "longitude",
      "word": 1,
      "start_bit": 23,
      "length": 24,
      "type": "scaled",
      "scale": 0.0000214577,
      "offset": -180.0,
      "maps_to": "position.lon"
    },
    {
      "name": "heading",
      "word": 2,
      "start_bit": 16,
      "length": 9,
      "type": "scaled",
      "scale": 0.703125,
      "offset": 0,
      "maps_to": "heading_deg"
    }
  ]
}
```

**Note:** The bit positions above are fabricated for illustration. Replace them with the real values from MIL-STD-6016.

## Checklist before submitting

- [ ] `label` and `sublabel` match the message type (J**X**.**Y** → label X, sublabel Y)
- [ ] `name` matches the PDF title for this message
- [ ] Every field has `name`, `word`, `start_bit`, `length`, and `type`
- [ ] Bit numbering is relative to the 57-bit data portion (subtract 13 if your PDF numbers from the full word)
- [ ] `scaled` fields have both `scale` and `offset`
- [ ] `enum` fields have a `values` dict with string keys
- [ ] `maps_to` uses a valid target from the table above
- [ ] No fields overlap within the same word
- [ ] Validation script passes with zero errors
