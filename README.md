# link16-parser

A stream processor for Link 16 tactical data link traffic. Reads PCAP captures (files or live pipes), parses J-series messages, maintains an in-memory track picture, and produces formatted tactical reports (TACREPs, 9-LINEs) via an interactive CLI or a network output stream.

> **This tool requires no external Python dependencies.** It runs on the standard library alone (Python 3.10+).

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

On a new machine, use the install script — it checks your Python version, installs the package, and ensures the command is on PATH:

```
bash install.sh
```

For manual installation, or on Windows where `install.sh` is not available, use `python3 -m pip` directly. Prefer this over bare `pip` or `pip3` — on systems with multiple Python versions they may point to different interpreters:

```
python3 -m pip install -e .          # Linux/Mac
python -m pip install -e .           # Windows
```

For development (adds pytest and pyright):

```
python3 -m pip install -e ".[dev]"   # Linux/Mac
python -m pip install -e ".[dev]"    # Windows
```

On Windows, if `link16-parser` is not found after install, add the Python `Scripts` folder to your PATH via System Properties → Environment Variables.

If `link16-parser` is not found after a manual install, see [Troubleshooting](#troubleshooting).

## Usage

### From a PCAP file

```
link16-parser --file capture.pcap
link16-parser --file capture.pcap --port 4444
link16-parser --file capture.pcap --encap simple
```

### From a live pipe

```
sudo tcpdump -i eth0 -w - | link16-parser --pipe
sudo tcpdump -i eth0 -w - udp port 4444 | link16-parser --pipe
ssh remote-host "tcpdump -i eth0 -w -" | link16-parser --pipe
```

The tool does not capture packets itself -- it reads PCAP data produced by external tools (tcpdump, tshark, dumpcap, etc.).

`sudo` is required for tcpdump to open the network interface, but applies only to tcpdump. `link16-parser` runs as your normal user on the right side of the pipe and requires no elevated privileges.

The `--pipe` flag is required when reading from stdin. Omitting it causes an error even if the pipe is set up correctly.

To find your interface name if `eth0` does not exist:

```
ip link show
# or
sudo tcpdump -D
```

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

---

## Troubleshooting

**`error: one of the arguments --file/-f --pipe/-p is required`**
You forgot `--pipe`. The tool requires an explicit flag to read from stdin:
```
sudo tcpdump -i eth0 -w - | link16-parser --pipe
```

**`tcpdump: eth0: You don't have permission to capture on that device`**
tcpdump needs root to open a network interface. Add `sudo` before `tcpdump` only — not before `link16-parser`:
```
sudo tcpdump -i eth0 -w - | link16-parser --pipe
```

**`tcpdump: eth0: No such device exists`**
`eth0` is not your interface name. Find the right one:
```
ip link show
```
Common alternatives: `ens3`, `ens160`, `enp0s3`, `wlan0`.

**`link16-parser: command not found` after a successful install**
pip installs the script to `~/.local/bin/` when running as a normal user, which is often not on PATH. Two options:

Add it to PATH permanently:
```
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
```

Or bypass PATH entirely using the module invocation (always works):
```
python3 -m link16_parser --file capture.pcap
python3 -m link16_parser --pipe
```

**`link16-parser: command not found` — package not installed**
Install it first:
```
pip install -e .
```
If you used `sudo su` to become root, root has a different Python environment. Run tcpdump as root and pipe to the parser as your normal user instead — no `sudo su` needed:
```
sudo tcpdump -i eth0 -w - | link16-parser --pipe
```
