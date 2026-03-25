# Architecture Overview

This tool is a **stream processor** for Link 16 tactical data link
traffic. It transforms raw PCAP data — whether from static capture
files or a live network pipe — into structured track data and formatted
tactical reports in real time. It is not a database of record — it
parses, correlates, and forwards, but does not durably store anything
itself.

---

## Where This Tool Fits

PCAP data is the input — either saved capture files (post-mission
analysis) or a live stream piped from `tcpdump` or similar (real-time
monitoring). Either way, the data arrives as unparsed binary packets
that can't be queried or displayed directly. This tool sits between
that raw PCAP input and whatever needs the parsed data — an operator
reading TACREPs, a remote system consuming a network feed, or a
durable database for post-mission playback.

```mermaid
flowchart LR
    A1["PCAP Files<br/>(saved captures)"] -->|"binary packets"| B["Link 16 Parser<br/>(stream processor)"]
    A2["Live PCAP Stream<br/>(tcpdump pipe)"] -->|"binary packets"| B
    B -->|"formatted reports"| C["Operator<br/>(interactive CLI)"]
    B -->|"structured data"| D["Network Consumer<br/>(TCP/UDP sink)"]
    B -->|"parsed tracks"| E["Durable Store<br/>(future)"]

    style E stroke-dasharray: 5 5
```

### Why there is no "SocketSource"

This tool **does not capture packets from the network**. It only reads
captures — either files on disk or a PCAP stream piped to stdin. The
actual packet capture is always performed by an external tool (tcpdump,
tshark, dumpcap, Wireshark, etc.).

This is a deliberate boundary:

- **No elevated privileges required.** Packet capture needs root or
  `CAP_NET_RAW`. This tool runs as a normal user.
- **No native dependencies.** Capture APIs are OS-specific (libpcap,
  AF_PACKET, WinPcap). This tool uses only the Python standard library.
- **Same tool for live and historical data.** A file from last month
  and a pipe from a live interface both enter as the same byte format.
- **Portability.** Runs anywhere Python runs, regardless of OS or
  network stack.

For live monitoring, the pattern is:

```
tcpdump -i eth0 -w - | link16-parser --pipe
```

The `-w -` flag tells tcpdump to write PCAP to stdout. The tool reads
it from stdin. The user sets up the capture; the tool handles the
parsing. This is a one-line setup, using tools operators are already
familiar with.

### Stateless across runs

The parser holds track state in memory for the duration of a session,
but nothing persists when the process exits. Re-processing a PCAP
produces identical output. This makes the tool a pure function of its
input: capture data in, structured track data out.

A durable store (SQLite, flat files, etc.) would plug in as another
output sink via the existing `OutputSink` / `on_update()` mechanism,
receiving every parsed track update without modifying the parser itself.

The next section explodes the "Link 16 Parser" box into its internal
pipeline stages.

---

## Internal Data Flow

The parser is a linear pipeline of components. Each component consumes
one data type and produces the next. No component knows the internals
of any other — they communicate only through the shared types defined
in `core/types.py` and the interfaces defined in `core/interfaces.py`.

```mermaid
flowchart LR
    A["Ingestion<br/><code>ingestion/</code>"] -->|"(timestamp, bytes)"| B["Encapsulation<br/><code>encapsulation/</code>"]
    B -->|"RawJWord[]"| C["Link 16<br/><code>link16/</code>"]
    C -->|"Link16Message[]"| D["Tracks<br/><code>tracks/</code>"]
    D -->|"Track"| E["Output<br/><code>output/</code>"]
    E -->|"string"| F["CLI<br/><code>cli/</code>"]
    D -->|"on_update"| G["Network<br/><code>network/</code>"]
    G -->|"formatted string"| E
```

### Component-by-component

| Component | Package | Interface | Input | Output | Notes |
|-----------|---------|-----------|-------|--------|-------|
| **Ingestion** | `ingestion/` | `PacketSource` | PCAP bytes (file or pipe) | `(float, bytes)` tuples | Strips Ethernet/IP headers. Optional `--port` filter. |
| **Encapsulation** | `encapsulation/` | `EncapsulationDecoder` | UDP/TCP payload bytes | `list[RawJWord]` | Pluggable: SIMPLE, SISO-J, JREAP-C (plugin), Auto |
| **Link 16** | `link16/` | `MessageDecoder` | `list[RawJWord]` | `list[Link16Message]` | Header parsing (public) + JSON-driven message decoding (injected at build/runtime) |
| **Tracks** | `tracks/` | — | `Link16Message` | `Track` (stored) | In-memory, thread-safe, keyed by STN. Push via `on_update()`. Optional TTL-based aging (ACTIVE → STALE → DROPPED). |
| **Output** | `output/` | `OutputFormatter` | `Track` | `str` | Pluggable: TACREP, 9-LINE, JSON, CSV, BULLSEYE |
| **CLI** | `cli/` | — | User commands | Formatted reports | Pull-based: queries Tracks, uses Output to format |
| **Network** | `network/` | `OutputSink` | `Track` (via callback) | Bytes over TCP/UDP | Push-based: uses Output to format, streams to remote endpoint |

---

## Python Module Map

Arrows point toward the dependency ("A → B" means A imports from B).
Every package also imports from `core/` — those arrows are omitted to
reduce clutter. `__main__.py` imports only from each package's
`__init__.py` facade — it never reaches into internal modules. Each
`__init__.py` owns the registry of its implementations and exposes a
factory function (e.g. `build_decoder()`, `build_parser()`).

```mermaid
graph TB
    core["<b>core/</b><br/>shared types + interfaces"]
    ingestion["<b>ingestion/</b><br/>PCAP file and pipe sources"]
    encapsulation["<b>encapsulation/</b><br/>SIMPLE, SISO-J, JREAP-C, Auto"]
    link16["<b>link16/</b><br/>J-word parser + message decoders"]
    tracks["<b>tracks/</b><br/>TrackDatabase (on_update callbacks)"]
    output["<b>output/</b><br/>TACREP, 9-LINE, JSON, CSV, BULLSEYE"]
    cli["<b>cli/</b><br/>InteractiveShell"]
    network["<b>network/</b><br/>NetworkSink (TCP/UDP)"]

    ingestion & encapsulation & link16 & tracks & output & cli & network -->|"imports"| core
    cli -->|"queries"| tracks
    cli -->|"uses"| output
    network -->|"uses"| output
```

Each box is a Python package. Internal structure (which files, which
classes) is covered in the component-by-component sections below.

---

## Threading Model

```mermaid
sequenceDiagram
    participant Main as main()
    participant Ingest as Ingestion Thread
    participant DB as TrackDatabase
    participant Aging as Aging Thread
    participant NetSink as NetworkSink Sender Thread
    participant Shell as InteractiveShell

    Main->>DB: start_aging (daemon thread)
    Main->>NetSink: start (daemon thread, optional)
    Main->>Ingest: start (daemon thread)
    Main->>Shell: run (foreground)

    loop until source exhausted or stop_event
        Ingest->>Ingest: read packet from source
        Ingest->>Ingest: decode encapsulation → RawJWords
        Ingest->>Ingest: parse J-words → Link16Messages
        Ingest->>DB: update(message) [acquires lock]
        DB->>DB: notify on_update listeners
        DB-->>NetSink: on_track_update → enqueue
    end

    loop every sweep_interval (aging)
        Aging->>DB: sweep_aging() [acquires lock]
        DB->>DB: transition ACTIVE→STALE→DROPPED
        DB-->>NetSink: on_track_update(track, None) → enqueue
    end

    loop background (NetworkSink sender)
        NetSink->>NetSink: dequeue formatted message
        NetSink->>NetSink: send over TCP/UDP
    end

    loop until quit/exit/Ctrl-C
        Shell->>Shell: read user command
        Shell->>DB: find(query) [acquires lock]
        DB-->>Shell: Track
        Shell->>Shell: format(Track) → string
        Shell-->>Shell: print to stdout
    end

    Shell->>Main: shell.run() returns
    Main->>Ingest: stop_event.set()
    Main->>DB: stop_aging()
    Main->>NetSink: stop()
```

The system uses up to four threads:

- **Ingestion thread** (daemon): reads packets, decodes, updates the
  track database. Sole writer to the DB.
- **Track aging thread** (daemon): periodic sweep that transitions
  tracks ACTIVE → STALE (after `stale_ttl`, default 120s) → DROPPED
  (after `stale_ttl + drop_ttl`, default 420s). Notifies listeners
  with `message=None`. New messages resurrect stale/dropped tracks.
- **CLI thread** (foreground): reads user commands, queries the DB.
  Sole interactive reader.
- **NetworkSink sender thread** (daemon, optional): drains a queue of
  formatted messages and sends them over TCP/UDP. Activated only when
  `--output-host` and `--output-port` are specified.

All threads share the `TrackDatabase`, protected by a single
`threading.Lock`. The `on_track_update()` callback runs inside the DB
lock and must not block — `NetworkSink` enqueues without waiting on I/O.

In `--pipe` mode, `PipeSource` consumes stdin for PCAP data, so the
interactive shell reads input from `/dev/tty` (the controlling terminal)
instead. If no terminal is available (cron, Docker, CI), the tool runs
in **headless mode**: ingestion only, no shell, exits when the source
is exhausted or on Ctrl-C.

---

## The CUI Boundary

This is the most important architectural line in the project. Everything
above it works with publicly documented specs. Everything below it
requires restricted standards — but is injected from external sources,
not built into this repo.

```mermaid
flowchart TB
    subgraph public["PUBLIC — this repo"]
        A["PCAP reader<br/>(with port filter)"]
        B["Encapsulation decoders<br/>(SIMPLE, DIS/SISO-J)"]
        C["J-word header parser<br/>(bits 0-12: word format,<br/>label, sublabel, MLI)"]
        D["Track database<br/>(with on_update callbacks)"]
        E["Output formatters<br/>(TACREP, 9-LINE, JSON, CSV, BULLSEYE)"]
        F["CLI shell"]
        H["Network sink<br/>(TCP/UDP streaming)"]
        I["DefinitionDecoder engine<br/>(generic JSON-driven decoder)"]
        J["Encapsulation plugin loader<br/>(importlib-based injection)"]
    end

    subgraph cui_6016["CUI — MIL-STD-6016 (separate repo)"]
        G["JSON message definitions<br/>(bit-field layouts for J2.2,<br/>J3.2, etc.)"]
    end

    subgraph cui_3011["CUI — MIL-STD-3011 (separate repo)"]
        K["JREAP-C decoder plugin<br/>(transport header parsing)"]
    end

    G -->|"injected via<br/>--definitions-dir"| I
    I -->|"DefinitionDecoder[]"| C
    C -->|"routes by<br/>(label, sublabel)"| I
    I -->|"Link16Message<br/>with populated fields"| D
    K -->|"injected via<br/>--encap-plugin"| J
    J -->|"replaces stub in<br/>decoder registry"| B

    style public fill:#1a1a2e,stroke:#4ecca3,stroke-width:3px,color:#e0e0e0
    style cui_6016 fill:#1a1a2e,stroke:#e74c3c,stroke-width:3px,color:#e0e0e0
    style cui_3011 fill:#1a1a2e,stroke:#e74c3c,stroke-width:3px,color:#e0e0e0
    style A fill:#2d3436,stroke:#4ecca3,color:#fff
    style B fill:#2d3436,stroke:#4ecca3,color:#fff
    style C fill:#2d3436,stroke:#4ecca3,color:#fff
    style D fill:#2d3436,stroke:#4ecca3,color:#fff
    style E fill:#2d3436,stroke:#4ecca3,color:#fff
    style F fill:#2d3436,stroke:#4ecca3,color:#fff
    style H fill:#2d3436,stroke:#4ecca3,color:#fff
    style I fill:#2d3436,stroke:#4ecca3,color:#fff
    style J fill:#2d3436,stroke:#4ecca3,color:#fff
    style G fill:#2d3436,stroke:#e74c3c,color:#fff
    style K fill:#2d3436,stroke:#e74c3c,color:#fff
```

Two CUI sources are injected at build or runtime:

- **MIL-STD-6016** (message field layouts): JSON definition files loaded
  via ``--definitions-dir`` or the ``LINK16_DEFINITIONS`` env var. The
  generic ``DefinitionDecoder`` reads these and extracts bit-fields from
  J-words. See ``docs/j-message-definition-transcription-guide_v2.md``.

- **MIL-STD-3011** (JREAP-C encapsulation): A Python package providing
  ``JreapCDecoder``, loaded via ``--encap-plugin`` or the
  ``LINK16_ENCAP_PLUGIN`` env var. See
  ``docs/mil-std-3011-jreap-c-plugin-guide.md`` and the template in
  ``docs/jreap-c-plugin-template/``.

No CUI data lives in this repo. Without injection, the parser runs but
produces no decoded messages (6016) and returns empty results for
JREAP-C packets (3011).

---

## Pluggable Extension Points

The architecture has five pluggable seams — places where you can add
new implementations without modifying existing code (beyond wiring).

| Extension Point | Protocol | Where to add | How to register |
|----------------|----------|--------------|-----------------|
| **Capture format** | — | `ingestion/` | New `*_reader.py` + magic bytes in `reader._auto_detect_stream()` |
| **Encapsulation format** | `EncapsulationDecoder` | `encapsulation/` | New module + `DECODER_REGISTRY` in `encapsulation/__init__.py` |
| **Encapsulation plugin** | `EncapsulationDecoder` | External package | `--encap-plugin` or `LINK16_ENCAP_PLUGIN` env var |
| **Message type** | `MessageDecoder` | JSON definition file | `--definitions-dir` or `LINK16_DEFINITIONS` env var |
| **Output format** | `OutputFormatter` | `output/` | New module + `build_formatters()` in `output/__init__.py` |
| **Output sink** | `OutputSink` | `network/` | New module + wiring in `__main__.py` |

Each component's `__init__.py` is the single entry point for that
package — it owns the registry of implementations and exposes a factory
function. `__main__.py` imports only from these facades, never from
internal modules. Each pluggable package has a detailed "How to extend"
guide in its `__init__.py` file.

---

## Key Design Decisions

**No external dependencies for core parsing.** The PCAP reader, header
parsing, and formatters use only the Python standard library (`struct`,
`dataclasses`, `threading`). This keeps the tool deployable on minimal
Linux environments without `pip install`.

**Auto-detection at every layer.** The same magic-bytes pattern is used
twice in the pipeline. At the ingestion layer, `reader._auto_detect_stream()`
reads the first 4 bytes of the capture to distinguish libpcap from pcapng
and dispatches to the right format-specific reader. At the encapsulation
layer, `AutoDecoder` inspects each packet's payload to determine SIMPLE
vs. DIS vs. JREAP-C. Users don't need to know or specify any of this —
it just works. Manual override is available via `--encap` for
encapsulation edge cases.

**Non-destructive track merging.** When `TrackDatabase.update()` receives
a message, it only overwrites fields that are non-None. A J2.2 PPLI
(which carries position but not identity) won't clobber the identity
previously set by a J3.2 Air Track. This means the track accumulates
the best-known state from all message types.

**Data-driven message decoding.** Message field layouts (MIL-STD-6016)
are defined in JSON files and loaded at runtime by a generic
`DefinitionDecoder`. This separates the CUI bit-field data from the
open-source tool — JSON files live in a separate repo and are injected
at build or runtime. Adding a new message type means writing a JSON
file, not Python code. A validation script (`scripts/validate_definitions.py`)
catches errors before runtime.

**Port filtering at ingestion.** The `--port` flag lets the PCAP reader
skip irrelevant traffic before it even reaches the encapsulation layer.
This is an optimization, not a requirement — without it, the pipeline
still handles arbitrary PCAPs correctly by silently skipping
non-matching packets at the encapsulation stage.

**Push-based output sinks.** The `TrackDatabase` notifies registered
listeners on every track update via `on_update()` callbacks. This
enables push-based output (e.g. streaming to a remote endpoint over
TCP/UDP) alongside the pull-based CLI. The `on_track_update()` callback
runs inside the DB lock, so sinks must be non-blocking — `NetworkSink`
uses a queue + background sender thread to achieve this.

**TTL-based track aging.** A background daemon thread inside
`TrackDatabase` periodically sweeps tracks and transitions them based
on silence duration. ACTIVE → STALE after `stale_ttl` (default 120s,
~10 missed PPLI cycles). STALE → DROPPED after `stale_ttl + drop_ttl`
(default 420s total). Dropped tracks remain in the database for history
queries but are hidden from `list` by default (`list all` shows them).
Aging transitions notify listeners with `message=None`, enabling sinks
to react to status changes. A new message arriving for a stale or
dropped track automatically resurrects it to ACTIVE. TTLs are
configurable at construction and at runtime via the CLI `config`
command.

---

## Design Considerations for Future Work

These are capabilities the architecture has been designed to accommodate
but that aren't built yet. Each entry describes *where the seam is* —
the module boundary or interface that would absorb the change — so that
future work extends the system rather than restructuring it.

**Durable storage / mission replay.** The tool is a stream processor —
PCAP in, structured data out — with no persistence across runs. A
durable store (SQLite, flat files, etc.) would plug in as an
`OutputSink` registered with `track_db.on_update()`. Two complementary
strategies: an *event log* (append every `Link16Message` for full
replay) and *state snapshots* (periodic `Track` dumps for cheap
queries). Both are consumers of the existing pipeline, not modifications
to it.

**Secondary indexes.** `TrackDatabase` lookups by callsign and track
number are O(n) linear scans today. If query volume or track count
grows, reverse-lookup dicts (maintained during `update()`) would make
these O(1). This is internal to `TrackDatabase` — no interface changes.

**Ingestion backpressure and observability.** For long-running live
streams, the ingestion thread has no way to signal that it's falling
behind. Stats (packets/sec, messages/sec, active track count) would
feed into a `status` CLI command and optionally into monitoring. The
`on_update()` callback mechanism could also surface queue-depth metrics
from network sinks.

---

## File Listing

```
link16-parser/
├── ARCHITECTURE.md              ← you are here
├── pyrightconfig.json           ← pyright strict mode config
├── link16_parser/
│   ├── __init__.py
│   ├── __main__.py              ← wiring + entry point
│   ├── core/
│   │   ├── types.py             ← shared data types (the pipeline's currency)
│   │   └── interfaces.py        ← Protocol definitions for pluggable modules
│   ├── ingestion/
│   │   ├── __init__.py          ← "How to add a capture format or source"
│   │   ├── reader.py            ← FileSource, PipeSource, format auto-detection
│   │   ├── pcap_reader.py       ← libpcap format stream reader
│   │   └── pcapng_reader.py     ← pcapng format stream reader (stub)
│   ├── encapsulation/
│   │   ├── __init__.py          ← decoder registry + plugin loader
│   │   ├── simple.py            ← STANAG 5602 (fully implemented)
│   │   ├── siso_j.py            ← DIS Signal PDU (fully implemented)
│   │   ├── jreap_c.py           ← MIL-STD-3011 (stub — replaced by plugin at runtime)
│   │   └── detect.py            ← auto-detection heuristic
│   ├── link16/
│   │   ├── __init__.py          ← build_parser() + definition loading
│   │   ├── parser.py            ← J-word header parsing + decoder registry
│   │   ├── definitions/         ← built-in definitions dir (populated at build time)
│   │   └── messages/
│   │       ├── __init__.py
│   │       ├── definition_decoder.py  ← generic JSON-driven field decoder
│   │       ├── loader.py              ← JSON loading + directory resolution
│   │       └── schema.py             ← JSON definition validation
│   ├── tracks/
│   │   ├── __init__.py          ← exports TrackDatabase
│   │   └── database.py          ← in-memory track store + TTL aging
│   ├── output/
│   │   ├── __init__.py          ← "How to add an output format"
│   │   ├── coords.py            ← decimal degrees ↔ military grid + shared utils
│   │   ├── tacrep_format.py     ← 5-line AIROP TACREP (formal military format)
│   │   ├── nineline_format.py   ← 9-line convenience format (informal)
│   │   ├── json_format.py       ← NDJSON (machine-readable, structured)
│   │   ├── csv_format.py        ← CSV (machine-readable, flat columns)
│   │   └── bullseye_format.py   ← Bullseye (bearing/distance from reference point)
│   ├── network/
│   │   ├── __init__.py          ← "How to add a network sink"
│   │   └── sink.py              ← TCP/UDP streaming sink
│   └── cli/
│       ├── __init__.py          ← exports InteractiveShell
│       └── shell.py             ← interactive CLI shell
├── scripts/
│   └── validate_definitions.py  ← standalone JSON definition validator
├── docs/
│   ├── j-message-definition-transcription-guide_v2.md
│   ├── mil-std-3011-jreap-c-plugin-guide.md
│   └── jreap-c-plugin-template/ ← copy-and-fill template for JREAP-C decoder
└── tests/
    ├── fixtures/                ← test JSON definitions (fabricated, non-CUI)
    ├── test_definition_decoder.py
    ├── test_definition_loader.py
    ├── test_schema_validation.py
    └── ...
```
