# JREAP-C Plugin Developer Guide

This guide is for the person implementing the JREAP-C (MIL-STD-3011) encapsulation decoder in the separate CUI repository. The decoder is written as a Python class and injected into the link16-parser tool at runtime.

## Quick start

A ready-to-use template is provided in [`jreap-c-plugin-template/`](jreap-c-plugin-template/). Copy the entire directory to your CUI repo and rename it. **The only file you need to modify is [`jreap_decoder/decoder.py`](jreap-c-plugin-template/jreap_decoder/decoder.py)** — everything else is ready to go.

```bash
cp -r docs/jreap-c-plugin-template/ /path/to/your-cui-repo/jreap-decoder
cd /path/to/your-cui-repo/jreap-decoder
pip install -e /path/to/link16-parser
pip install -e .
```

Then open `jreap_decoder/decoder.py`, find the `decode()` method, and fill in the TODO section using MIL-STD-3011.

## What you need to modify

### `jreap_decoder/decoder.py` — the decoder class

This file contains a skeleton `JreapCDecoder` class. The `decode()` method has TODO comments with a step-by-step guide showing exactly what to fill in:

1. **Constants** (top of file) — fill in the header sizes from MIL-STD-3011:
   ```python
   TBH_LEN = ??           # Transmission Block Header length in bytes
   MGH_LEN = ??           # Message Group Header length in bytes
   APP_HEADER_LEN = ??    # Application Header length in bytes
   ```

2. **Validation** — check minimum payload length and any magic/version bytes that identify JREAP-C packets.

3. **Header parsing** — use `struct.unpack_from()` to extract NPG, STN, and word count from the correct offsets in the TBH, MGH, and Application Headers.

4. **J-word extraction** — slice 10-byte chunks from the payload after the headers. The commented-out code in the template shows the exact loop pattern.

### `tests/test_jreap_c.py` — tests

The test file has a helper function `_make_jreap_c_payload()` that you need to fill in — it constructs synthetic JREAP-C packets for testing. Several test cases are provided but commented out; uncomment them as you implement the decoder.

### Files you do NOT need to modify

| File | What it does | Status |
|---|---|---|
| [`pyproject.toml`](jreap-c-plugin-template/pyproject.toml) | Package metadata, dependencies | Ready |
| [`jreap_decoder/__init__.py`](jreap-c-plugin-template/jreap_decoder/__init__.py) | Package marker | Ready |
| [`tests/__init__.py`](jreap-c-plugin-template/tests/__init__.py) | Test package marker | Ready |
| [`README.md`](jreap-c-plugin-template/README.md) | Usage instructions | Ready |

## RawJWord — what you produce

Each extracted J-word becomes a `RawJWord`:

```python
RawJWord(
    data=payload[start:end],  # Exactly 10 bytes (80 bits)
    stn=stn,                  # Source Track Number (0-32767), from JREAP-C headers
    npg=npg,                  # Network Participation Group (0-511), from JREAP-C headers
    timestamp=datetime.fromtimestamp(pcap_timestamp, tz=timezone.utc),
)
```

## Activation

After installing, tell link16-parser where to find your decoder:

**CLI argument (highest precedence):**
```bash
python -m link16_parser --file capture.pcap --encap-plugin jreap_decoder.decoder
```

**Environment variable:**
```bash
export LINK16_ENCAP_PLUGIN=jreap_decoder.decoder
python -m link16_parser --file capture.pcap
```

The value `jreap_decoder.decoder` is the dotted Python module path — it maps to the file `jreap_decoder/decoder.py`.

## How auto-detection works

When `--encap auto` is used (the default), the tool tries each encapsulation format:

1. **SIMPLE** — checks for sync bytes `0x49 0x36` at the start
2. **SISO-J** — checks for DIS PDU type `0x1A` at byte 2
3. **Fallback loop** — tries each remaining decoder (including JREAP-C), returns first non-empty result

Your `decode()` method must reliably return `[]` for non-JREAP-C payloads to avoid false positives in auto-detection.

## What happens if the plugin fails to load

The tool never crashes due to a plugin problem. If the module can't be imported, the class is missing, or instantiation fails, a warning is logged and the built-in stub (which returns `[]`) is used instead.

## Reference implementation

The SIMPLE decoder in `link16_parser/encapsulation/simple.py` (~100 lines) is the gold-standard reference. It demonstrates the complete pattern:

1. Validate format-specific header bytes → return `[]` if wrong
2. Parse header fields (NPG, STN, word count) using `struct.unpack_from()`
3. Slice out 10-byte J-word chunks
4. Construct `RawJWord` objects
5. Return `[]` for any validation failure

Your JREAP-C decoder follows the same pattern — the only difference is the header layout.

## Type checking

The template includes a protocol conformance check at the bottom of `decoder.py`:

```python
_: EncapsulationDecoder = JreapCDecoder()
```

Run pyright to verify:
```bash
pyright --pythonversion 3.12 jreap_decoder/
```

## Checklist

- [ ] Copied template to CUI repo
- [ ] Filled in header size constants from MIL-STD-3011
- [ ] Implemented `decode()` — validate headers, parse NPG/STN/word count, extract J-words
- [ ] `decode()` returns `[]` for non-JREAP-C payloads (never raises)
- [ ] Filled in `_make_jreap_c_payload()` test helper
- [ ] Uncommented and passing all tests in `test_jreap_c.py`
- [ ] `pip install -e .` succeeds
- [ ] `pyright --pythonversion 3.12 jreap_decoder/` passes
- [ ] `python -m link16_parser --file capture.pcap --encap-plugin jreap_decoder.decoder --verbose` works
