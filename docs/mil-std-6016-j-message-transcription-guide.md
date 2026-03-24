# Message Definition Transcription Guide

This guide walks you through creating a JSON message definition file from the MIL-STD-6016 PDF. Each file defines one message type (e.g., J3.2 Air Track). No programming knowledge is required.

---

## Transcription priority

Not all messages have equal operational value. If you are working through the catalog manually, transcribe in this order:

**Tier 1 — do these first:**
J2.2, J3.2, J12.0, J12.1, J12.6, J7.0, J10.2, J7.4, J3.5, J2.5

**Tier 2 — operational completeness:**
J9.0, J7.2, J7.5, J12.2, J13.2, J10.3, J12.5, J1.2, J3.0, J14.0

**Tier 3 — full coverage:**
J12.3, J12.4, J12.7, J14.2, J15.0, J10.5, J10.6, J11.0, J11.1, J11.2,
J3.7, J3.3, J7.1, J7.3, J7.6, J7.7, J8.0, J8.1, J6.0, J13.0, J3.6,
J3.4, J2.3, J2.0, J1.0, J1.3, J1.5, J1.6, J28.2, J31.7

See the decoder priority analysis document for full rationale.

---

## What you need

- The MIL-STD-6016 PDF (Section 5), open to the message type you are transcribing
- A text editor (VS Code, Notepad++, etc.)
- The validation tool (instructions at the end)

---

## Document structure

Section 5 contains all message definitions, split across six parts:

| Part | Messages      | Approx. starting page |
|------|---------------|-----------------------|
| 5.1  | J0 – J6       | 538                   |
| 5.2  | J7 – J12      | 2020                  |
| 5.3  | J13 – RTT     | 4112                  |
| 5.4 – 5.6 | Remaining messages | —            |

To jump directly to any message, search the PDF for its label notation exactly as written: `J2.2`, `J3.2`, etc. Section headers use this format precisely.

---

## Structure of a message definition in the PDF

Each message type contains **four sections** in this order. Knowing which section is which prevents the most common transcription errors.

### 1. Applicability Table

One table covers an entire message *family* — for example, Table J0-1 covers all J0.x sublabels. It shows which words exist (Initial, Extension, Continuation 1–N) for each sublabel.

**Use this first.** Check it before you start transcribing so you know how many words the message has and how many Word Description tables to expect.

The word notation used in this table matches what you will see on the Word Description pages:

| Applicability Table entry | Word suffix in PDF | `word` value in JSON |
|---|---|---|
| INITIAL WORD | `I` (e.g., `J0.0I`) | `0` |
| EXTENSION WORD | `E` (e.g., `J0.0E`) | treat as next continuation |
| CONTINUATION WORD – 1 | `C1` (e.g., `J0.0C1`) | `1` |
| CONTINUATION WORD – 2 | `C2` | `2` |
| CONTINUATION WORD – N | `CN` | `N` |

### 2. Message Summary

Contains a PURPOSE paragraph and a DATA ELEMENT SUMMARY table. The summary table lists field names and bit *counts* only — **no bit positions**.

> ⚠️ **Do not transcribe from this table.** It looks like a field list but is missing the position data you need. Skip past it entirely.

### 3. Word Map

An ASCII diagram showing field names laid out visually across bit positions for each word. Example header:

```
WORD MAP
--------
WORD NUMBER:  J0.0I
WORD TITLE:   INITIAL ENTRY INITIAL WORD

  24: 23: 22  21  20  19  18  17 16: 15  14  13: 12  11  10: 09  08 ...
```

**Use this as a sanity check only, not as your transcription source.** After completing a Word Description, verify that your field layout matches the visual diagram.

> ⚠️ **Critical:** Bits in the Word Map run **right to left** within each row. Bit 00 is on the far right of the first row. This is the opposite of what most programmers expect. Do not read bit positions directly from this diagram — use the Word Description table instead.

### 4. Word Description

The tabular data you transcribe from. You will see one of these per word (Initial, Continuation 1, Continuation 2, etc.). It always begins with this header:

```
WORD DESCRIPTION
----------------
WORD NUMBER:  J0.0I
WORD TITLE:   INITIAL ENTRY INITIAL WORD

REFERENCE
DFI/DUI    DATA FIELD DESCRIPTOR    BIT POSITION    # BITS    RESOLUTION, CODING, ETC
```

**This is your transcription source.** The columns mean:

| Column | What it means |
|---|---|
| **DFI/DUI** | Unique numeric field identifier — note it for cross-referencing but you do not need it in the JSON |
| **DATA FIELD DESCRIPTOR** | The field name |
| **BIT POSITION** | Where the field starts within the word — see the bit numbering section below |
| **# BITS** | Field width in bits |
| **RESOLUTION, CODING, ETC** | Encoding: binary, octal, scaling factor, enumerated code table, or SPARE |

To jump directly to these tables, search the PDF for **`WORD DESCRIPTION`**.

---

## Quick overview of the JSON format

A Link 16 message is made of one or more **J-words**. Each J-word is 80 bits:

```
[ 13-bit header | 57-bit data | 5-bit parity | 5-bit pad ]
```

You are transcribing the fields within the **57-bit data** portion only. The header, parity, and padding are handled automatically — ignore them.

---

## Step 1: Identify the message

Find the message in the PDF using the Applicability Table for its family. Note three things:

- **Label** — the number before the dot (J**3**.2 → label `3`)
- **Sublabel** — the number after the dot (J3.**2** → sublabel `2`)
- **Name** — the full name from the Message Summary title (e.g., "J3.2 Air Track")
- **Word count** — from the Applicability Table, how many words does this sublabel have?

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

---

## Step 2: Locate and read the Word Description tables

1. Search the PDF for `WORD DESCRIPTION`
2. Confirm the WORD NUMBER matches the message and word you expect (e.g., `J3.2I` for the Initial word)
3. Read each row in the table — one row = one field entry in your JSON
4. Repeat for each continuation word (C1, C2, etc.) as identified in the Applicability Table
5. After completing each word, cross-check your field layout against the Word Map as a sanity check

---

## Step 3: Transcribe each field

For each row in the Word Description table, add an entry to the `"fields"` array.

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
| `name` | A short, descriptive name. Use lowercase with underscores. Your choice — it is just for readability. |
| `word` | `0` for the Initial word, `1` for C1, `2` for C2, etc. |
| `start_bit` | Bit position within the 57-bit data portion. **Bit 0 is the first data bit.** See the bit numbering section below. |
| `length` | Number of bits from the `# BITS` column. |
| `type` | See the type guide below. |

### Handling SPARE and DISUSED fields

Fields labeled **SPARE** or **DISUSED** in the Word Description table are unused bit regions. **Do not create a JSON entry for them** — skip those rows entirely. Your `start_bit` arithmetic for subsequent fields must still account for their width so that later fields land at the correct positions.

---

## Bit numbering — the most important section

### The offset rule

The 57-bit data portion starts at **bit 13** of the full 80-bit word. All `start_bit` values in the JSON are relative to the data portion, not the full word.

**General rule: `start_bit = pdf_bit_position - 13`**

Examples:
- PDF says bit position 13 → `"start_bit": 0`
- PDF says bit position 16 → `"start_bit": 3`
- PDF says bit positions 20–28 → `"start_bit": 7, "length": 9`

### Check which convention your PDF uses

Some editions number fields within the data portion already (starting from 0). Before transcribing any message:

1. Look at the first non-SPARE field in a Word Description
2. If BIT POSITION is `0` → use the numbers as-is, no subtraction needed
3. If BIT POSITION is `13` → subtract 13 from every BIT POSITION value

Confirm this once at the start of each session. It is consistent throughout the document.

### Do not use the Word Map for bit positions

The Word Map diagram runs bits right-to-left. The Word Description table runs them left-to-right in the conventional sense. Always take positions from the Word Description table.

> **Tip:** If the validator reports overlapping fields or bit ranges exceeding 57, the most likely cause is either reading bit counts from the Data Element Summary instead of bit positions from the Word Description, or forgetting to subtract 13 when your PDF uses full-word numbering.

---

## Step 4: Choose the right type

### `integer` — raw numeric value

Use when the field is a plain number with no conversion needed.

```json
{
  "name": "track_quality",
  "word": 0, "start_bit": 0, "length": 4,
  "type": "integer",
  "maps_to": "fields.track_quality"
}
```

### `scaled` — value with a formula

Use when the PDF gives a resolution or conversion factor. Common for latitude, longitude, altitude, heading, and speed.

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

**How to find `scale` and `offset` from the PDF:**

The RESOLUTION, CODING, ETC column will state something like:
- "Resolution: 0.703125 degrees/LSB" → `"scale": 0.703125, "offset": 0`
- "Range: -90 to +90, 23-bit unsigned" → `scale` = 180 / (2²³ − 1), `offset` = −90.0
- "Range: 0 to 360 degrees, 9-bit" → `scale` = 360 / 512, `offset` = 0

If the PDF gives a range [min, max] with N bits:
- `scale` = (max − min) / (2ᴺ − 1)
- `offset` = min

Both `scale` and `offset` are **required** for the `scaled` type. If there is no offset, use `0`.

### `enum` — coded value with named meanings

Use when the RESOLUTION, CODING, ETC column lists a table of codes (e.g., 0 = PENDING, 1 = UNKNOWN, ...).

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

**Important:** The keys in `"values"` must be **strings** (with quotes), even though they represent numbers. Copy every code from the PDF table. If a code is listed as "Reserved" or "Spare", omit it.

Note that Link 16 field values are frequently expressed in **octal** in the PDF. If the coding table shows octal values (e.g., 000, 001, 002 octal), convert them to decimal for the JSON keys.

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

Use when the field is a set of bit flags that do not need individual decoding. The raw integer value is stored as-is.

```json
{
  "name": "status_flags",
  "word": 0, "start_bit": 12, "length": 6,
  "type": "flags",
  "maps_to": "fields.status_flags"
}
```

---

## Step 5: Set `maps_to`

The `maps_to` key tells the parser where to put the decoded value on the output message. It is optional — if omitted, the field is decoded but not mapped to any output.

| Target | Use for |
|---|---|
| `identity` | Friend/hostile/neutral identification |
| `heading_deg` | Heading in degrees |
| `speed_kph` | Speed in km/h |
| `callsign` | Platform callsign |
| `track_number` | Track number |
| `position.lat` | Latitude (requires `position.lon` in the same message) |
| `position.lon` | Longitude (requires `position.lat` in the same message) |
| `position.alt_m` | Altitude in metres |
| `platform.generic_type` | Platform type (e.g., "FTR", "BMR") |
| `platform.specific_type` | Specific platform type |
| `platform.nationality` | Platform nationality |
| `fields.xxx` | Anything else — replace `xxx` with a descriptive name |

**Position requires both `lat` and `lon`** to appear in the same message. If only one is present, the position is dropped. `alt_m` is optional.

---

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

Fix any errors it reports and re-run until it passes with zero errors.

---

## Rules and constraints

1. **One file per message type.** File naming is up to you, but `j3_2.json` is the standard convention.
2. **Fields cannot span word boundaries.** If a logical value is split across two words in the PDF, create two separate fields (one per word) and map them both to `fields.xxx`. The parser handles each word independently.
3. **`start_bit + length` must not exceed 57.** The data portion is 57 bits (bits 13–69 of the 80-bit word). If your field exceeds this, double-check your bit numbering.
4. **No two fields in the same word can overlap.** The validator catches this.
5. **Enum keys are strings.** Write `"3": "FRIEND"`, not `3: "FRIEND"`.
6. **Skip SPARE and DISUSED rows.** Do not create JSON entries for them.

---

## Complete example

Here is a full (fabricated) definition for a J3.2 Air Track message with three words:

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
      "name": "track_number",
      "word": 0,
      "start_bit": 7,
      "length": 25,
      "type": "track_num",
      "maps_to": "track_number"
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
      "name": "altitude",
      "word": 2,
      "start_bit": 0,
      "length": 16,
      "type": "scaled",
      "scale": 30.48,
      "offset": -1524.0,
      "maps_to": "position.alt_m"
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
    },
    {
      "name": "platform_type",
      "word": 2,
      "start_bit": 25,
      "length": 4,
      "type": "enum",
      "values": {
        "0": "UNKNOWN",
        "1": "FTR",
        "2": "BMR",
        "3": "RECCE",
        "4": "TANKER",
        "5": "AEW",
        "6": "HELO"
      },
      "maps_to": "platform.generic_type"
    }
  ]
}
```

**Note:** All bit positions and scale values above are fabricated for illustration. Replace them with the real values from MIL-STD-6016.

---

## Checklist before submitting

- [ ] Consulted the Applicability Table to confirm how many words this sublabel has
- [ ] Transcribed from the **Word Description** table, not the Data Element Summary or Word Map
- [ ] `label` and `sublabel` match the message type (J**X**.**Y** → label X, sublabel Y)
- [ ] `name` matches the PDF title for this message
- [ ] Every field has `name`, `word`, `start_bit`, `length`, and `type`
- [ ] Determined whether the PDF numbers bits from 0 (data-relative) or 13 (full-word), and applied the −13 offset if needed
- [ ] SPARE and DISUSED rows are skipped
- [ ] `scaled` fields have both `scale` and `offset`
- [ ] `enum` fields have a `values` dict with string keys; octal PDF values converted to decimal
- [ ] `maps_to` uses a valid target from the table in Step 5
- [ ] No fields overlap within the same word
- [ ] Field layout visually matches the Word Map diagram for each word
- [ ] Validation script passes with zero errors
