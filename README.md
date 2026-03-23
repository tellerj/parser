# link16-parser

A stream processor for Link 16 tactical data link traffic. Reads PCAP captures (files or live pipes), parses J-series messages, maintains an in-memory track picture, and produces formatted tactical reports (TACREPs, 9-LINEs) via an interactive CLI or a network output stream.

> **This tool requires no external Python dependencies.** It runs on the standard library alone (Python 3.11+).

---

## Important: Message Decoders Not Included

**This repository does not ship with J-series message decoders.** The full pipeline (PCAP ingestion, encapsulation decoding, J-word header parsing, track database, output formatting) is implemented and functional, but the message-specific field decoders that extract tactical data (position, identity, platform type, callsign, etc.) from the 57-bit data portion of each J-word require access to MIL-STD-6016, which is a restricted standard.

The decoders included here are **stubs** -- they parse the public J-word envelope (word format, label, sublabel, MLI) but return messages with all tactical fields set to `None`.

To obtain functional message decoders, see: **[TODO: link to decoder repository]**

Once you have them, drop the decoder modules into `link16_parser/link16/messages/` and register them in `link16_parser/link16/__init__.py`. No other files need to change.

---

## What It Does

- Reads **libpcap** and **pcapng** captures from files or live stdin pipes
- Auto-detects capture format and encapsulation (SIMPLE / STANAG 5602, DIS / SISO-J, JREAP-C)
- Parses J-word headers and routes messages to registered decoders
- Maintains an in-memory track picture, merging updates from multiple message types
- Formats tracks as **5-line AIROP TACREPs** or **9-LINE** reports
- Optionally streams formatted output over **TCP or UDP** to a remote endpoint
- Runs with **zero external dependencies** on any system with Python 3.11+

## Installation

```
pip install -e .
```

Or for development (adds pytest and pyright):

```
pip install -e ".[dev]"
```

## Usage

### From a PCAP file

```
link16-parser --file capture.pcap
link16-parser --file capture.pcap --port 4444
link16-parser --file capture.pcap --encap simple
```

### From a live pipe

```
tcpdump -i eth0 -w - | link16-parser --pipe
tcpdump -i eth0 -w - udp port 4444 | link16-parser --pipe
ssh remote-host "tcpdump -i eth0 -w -" | link16-parser --pipe
```

The tool does not capture packets itself -- it reads PCAP data produced by external tools (tcpdump, tshark, dumpcap, etc.).

### With network output

```
link16-parser --file capture.pcap --output-host 192.168.1.10 --output-port 9000
link16-parser --file capture.pcap --output-host 10.0.0.5 --output-port 5000 --output-proto udp
```

### Interactive shell

Once running, you get an interactive prompt:

```
>> list                  # show all tracked entities
>> tacrep VIPER01        # generate TACREP by callsign
>> 9line 100             # generate 9-line by STN
>> info A1234            # show raw track data by track number
>> format 9-LINE         # switch default output format
>> help                  # show all commands
>> quit                  # exit
```

Tracks can be looked up by STN (number), callsign (case-insensitive), or track number.

### All options

```
link16-parser --help
```

## Running Tests

```
pytest
```
