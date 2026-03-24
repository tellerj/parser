# JREAP-C Decoder Plugin

JREAP-C (MIL-STD-3011) encapsulation decoder for [link16-parser](https://github.com/your-org/link16-parser).

## Setup

```bash
# Install link16-parser first
pip install -e /path/to/link16-parser

# Install this plugin
pip install -e .
```

## Usage

```bash
# Activate via CLI argument
python -m link16_parser --file capture.pcap --encap-plugin jreap_decoder.decoder

# Or via environment variable
export LINK16_ENCAP_PLUGIN=jreap_decoder.decoder
python -m link16_parser --file capture.pcap
```

## Development

The only file you need to modify is `jreap_decoder/decoder.py`. It contains
a skeleton `JreapCDecoder` class with TODO comments showing exactly what to
fill in from MIL-STD-3011.

Run tests:
```bash
pip install pytest
python -m pytest tests/ -v
```

Type check:
```bash
pip install pyright
pyright --pythonversion 3.12 jreap_decoder/
```
