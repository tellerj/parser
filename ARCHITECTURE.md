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

The parser is stateless across runs — it holds track state in memory
for the duration of a session, but nothing persists when the process
exits. Re-processing a PCAP produces identical output. This makes the
tool a pure function of its input: PCAP in, structured data out.

A durable store (SQLite, flat files, etc.) would plug in as another
output sink via the existing `OutputSink` / `on_update()` mechanism,
receiving every parsed track update without modifying the parser itself.

The next section explodes the "Link 16 Parser" box into its internal
pipeline stages.

---

## Internal Data Flow

The parser is a linear pipeline. Each stage consumes one data type and
produces the next. No stage knows the internals of any other — they
communicate only through the shared types defined in `core/types.py`.

```mermaid
flowchart LR
    A["PCAP Source<br/>(file or stdin pipe)"] -->|"(timestamp, bytes)"| B["Encapsulation<br/>Decoder"]
    B -->|"RawJWord[]"| C["J-Word<br/>Parser"]
    C -->|"Link16Message[]"| D["Track<br/>Database"]
    D -->|"Track"| E["Output<br/>Formatter"]
    E -->|"string"| F["User<br/>(interactive CLI)"]
    D -->|"on_update callback"| G["Network<br/>Sink"]
    G -->|"formatted string"| H["Remote<br/>Endpoint"]
```

### Stage-by-stage

| Stage | Package | Input | Output | Notes |
|-------|---------|-------|--------|-------|
| **Ingestion** | `ingestion/` | PCAP bytes (file or pipe) | `(float, bytes)` tuples | Strips Ethernet/IP/UDP\|TCP headers. Optional `--port` filter. |
| **Encapsulation** | `encapsulation/` | UDP/TCP payload bytes | `list[RawJWord]` | Pluggable: SIMPLE, SISO-J, JREAP-C, Auto |
| **J-Word Parsing** | `link16/` | `list[RawJWord]` | `list[Link16Message]` | Header parsing (public) + message decoding (needs MIL-STD-6016) |
| **Track DB** | `tracks/` | `Link16Message` | `Track` (stored) | In-memory, thread-safe, keyed by STN. Push notifications via `on_update()`. |
| **Formatting** | `output/` | `Track` | `str` | Pluggable: TACREP, 9-LINE, future formats |
| **CLI** | `cli/` | User commands | Formatted reports | Interactive shell, queries the Track DB (pull-based) |
| **Network Streaming** | `network/` | `Track` (via callback) | Formatted bytes over TCP/UDP | Push-based: reacts to every track update via `on_update()` |

---

## Module Map

```mermaid
graph TD
    subgraph core["core/"]
        types["types.py<br/>─────────<br/>Position, PlatformId,<br/>RawJWord, Link16Message,<br/>Track, Identity, WordFormat"]
        interfaces["interfaces.py<br/>─────────<br/>PacketSource,<br/>EncapsulationDecoder,<br/>MessageDecoder,<br/>OutputFormatter,<br/>OutputSink"]
    end

    subgraph ingestion["ingestion/"]
        pcap["pcap_reader.py<br/>─────────<br/>PcapFileSource<br/>PcapPipeSource<br/>(optional port filter)"]
    end

    subgraph encapsulation["encapsulation/"]
        simple["simple.py<br/>SimpleDecoder"]
        sisoj["siso_j.py<br/>SisoJDecoder"]
        jreapc["jreap_c.py<br/>JreapCDecoder ⚠️ stub"]
        detect["detect.py<br/>AutoDecoder"]
    end

    subgraph link16["link16/"]
        parser["parser.py<br/>JWordParser"]
        subgraph messages["messages/"]
            j22["j2_2.py<br/>J2.2 Air PPLI ⚠️"]
            j32["j3_2.py<br/>J3.2 Air Track ⚠️"]
            j282["j28_2.py<br/>J28.2 Free Text ⚠️"]
        end
    end

    subgraph tracks["tracks/"]
        db["database.py<br/>TrackDatabase<br/>(on_update callbacks)"]
    end

    subgraph output["output/"]
        coords["coords.py<br/>coordinate conversion"]
        tacrep["tacrep.py<br/>TacrepFormatter"]
        nineline["nineline.py<br/>NineLineFormatter"]
    end

    subgraph network["network/"]
        netsink["sink.py<br/>NetworkSink<br/>(TCP/UDP streaming)"]
    end

    subgraph cli["cli/"]
        shell["shell.py<br/>InteractiveShell"]
    end

    main["__main__.py<br/>wiring + entry point"]

    pcap --> detect
    detect --> simple & sisoj & jreapc
    detect --> parser
    parser --> j22 & j32 & j282
    parser --> db
    db --> shell
    db -.->|"on_update"| netsink
    netsink --> tacrep
    shell --> tacrep & nineline
    tacrep --> coords
    nineline --> coords
    main -.->|"wires"| pcap & detect & parser & db & shell & netsink
```

Items marked **⚠️** are stubs awaiting MIL-STD-6016 access.

---

## Threading Model

```mermaid
sequenceDiagram
    participant Main as main()
    participant Ingest as Ingestion Thread
    participant DB as TrackDatabase
    participant NetSink as NetworkSink Sender Thread
    participant Shell as InteractiveShell

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
    Main->>NetSink: stop()
```

The system uses up to three threads:

- **Ingestion thread** (daemon): reads packets, decodes, updates the
  track database. Sole writer to the DB.
- **CLI thread** (foreground): reads user commands, queries the DB.
  Sole interactive reader.
- **NetworkSink sender thread** (daemon, optional): drains a queue of
  formatted messages and sends them over TCP/UDP. Activated only when
  `--output-host` and `--output-port` are specified.

All threads share the `TrackDatabase`, protected by a single
`threading.Lock`. The `on_track_update()` callback runs inside the DB
lock and must not block — `NetworkSink` enqueues without waiting on I/O.

---

## The MIL-STD-6016 Boundary

This is the most important architectural line in the project. Everything
above it works with publicly documented specs. Everything below it
requires the restricted standard.

```mermaid
flowchart TB
    subgraph public["✅ PUBLIC — works today"]
        A["PCAP reader<br/>(with port filter)"]
        B["Encapsulation decoders<br/>(SIMPLE, DIS/SISO-J)"]
        C["J-word header parser<br/>(bits 0-12: word format,<br/>label, sublabel, MLI)"]
        D["Track database<br/>(with on_update callbacks)"]
        E["TACREP / 9-LINE formatters"]
        F["CLI shell"]
        H["Network sink<br/>(TCP/UDP streaming)"]
    end

    subgraph restricted["🔒 REQUIRES MIL-STD-6016"]
        G["Message-specific field decoding<br/>(bits 13-69: lat, lon, alt,<br/>speed, heading, identity,<br/>platform type, callsign)"]
    end

    C -->|"routes by<br/>(label, sublabel)"| G
    G -->|"Link16Message<br/>with populated fields"| D

    style public fill:#1a1a2e,stroke:#4ecca3,stroke-width:3px,color:#e0e0e0
    style restricted fill:#1a1a2e,stroke:#e74c3c,stroke-width:3px,color:#e0e0e0
    style A fill:#2d3436,stroke:#4ecca3,color:#fff
    style B fill:#2d3436,stroke:#4ecca3,color:#fff
    style C fill:#2d3436,stroke:#4ecca3,color:#fff
    style D fill:#2d3436,stroke:#4ecca3,color:#fff
    style E fill:#2d3436,stroke:#4ecca3,color:#fff
    style F fill:#2d3436,stroke:#4ecca3,color:#fff
    style H fill:#2d3436,stroke:#4ecca3,color:#fff
    style G fill:#2d3436,stroke:#e74c3c,color:#fff
```

**When MIL-STD-6016 becomes available**, the only files that change are
the message decoders in `link16/messages/` (e.g. `j2_2.py`, `j3_2.py`).
No other module is affected.

---

## Pluggable Extension Points

The architecture has four pluggable seams — places where you can add
new implementations without modifying existing code (beyond wiring).

| Extension Point | Protocol | Where to add | How to register |
|----------------|----------|--------------|-----------------|
| **Encapsulation format** | `EncapsulationDecoder` | `encapsulation/` | `detect.py` + `__main__.py` |
| **Message type decoder** | `MessageDecoder` | `link16/messages/` | `__main__.py` → `parser.register()` |
| **Output format** | `OutputFormatter` | `output/` | `__main__.py` → `formatters` dict |
| **Output sink** | `OutputSink` | `network/` | `__main__.py` → `track_db.on_update()` |

Each pluggable package has a detailed "How to extend" guide in its
`__init__.py` file.

---

## Key Design Decisions

**No external dependencies for core parsing.** The PCAP reader, header
parsing, and formatters use only the Python standard library (`struct`,
`dataclasses`, `threading`). This keeps the tool deployable on minimal
Linux environments without `pip install`.

**Auto-detection over configuration.** The `AutoDecoder` inspects each
packet's magic bytes to determine the encapsulation format. Users don't
need to know (or specify) whether the capture uses SIMPLE vs.
DIS vs. JREAP-C — it just works. Manual override is available via
`--encap` for edge cases.

**Non-destructive track merging.** When `TrackDatabase.update()` receives
a message, it only overwrites fields that are non-None. A J2.2 PPLI
(which carries position but not identity) won't clobber the identity
previously set by a J3.2 Air Track. This means the track accumulates
the best-known state from all message types.

**Stubs over dead code.** The message decoders exist as real classes
that return real `Link16Message` objects — they just don't populate
the fields yet. This means the full pipeline runs end-to-end today
(ingestion → parsing → track DB → TACREP output), and filling in the
field decoding is a matter of writing bit-extraction code inside the
existing `decode()` methods.

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

---

## Design Considerations for Future Work

These are capabilities the architecture has been designed to accommodate
but that aren't built yet. Each entry describes *where the seam is* —
the module boundary or interface that would absorb the change — so that
future work extends the system rather than restructuring it.

**Track lifecycle (aging / expiry).** The `Track` dataclass carries a
`status` field (`ACTIVE` / `STALE` / `DROPPED`) and a `last_updated`
timestamp. Today all tracks are `ACTIVE` forever. A TTL-based aging
policy would live inside `TrackDatabase` — a periodic sweep that
transitions tracks to `STALE` after N minutes without an update, then
`DROPPED` after a further interval. Formatters and the CLI can filter
on `status` without any interface changes. A pre-drop notification to
sinks (via `on_update()`) would let a durable store capture final state.

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
├── pyproject.toml               ← package metadata, CLI entry point
├── link16_parser/
│   ├── __init__.py
│   ├── __main__.py              ← wiring + entry point
│   ├── core/
│   │   ├── types.py             ← shared data types (the pipeline's currency)
│   │   └── interfaces.py        ← Protocol definitions for pluggable modules
│   ├── ingestion/
│   │   └── pcap_reader.py       ← PCAP file + stdin pipe sources
│   ├── encapsulation/
│   │   ├── __init__.py          ← "How to add an encapsulation format"
│   │   ├── simple.py            ← STANAG 5602 (fully implemented)
│   │   ├── siso_j.py            ← DIS Signal PDU (fully implemented)
│   │   ├── jreap_c.py           ← MIL-STD-3011 (stub)
│   │   └── detect.py            ← auto-detection heuristic
│   ├── link16/
│   │   ├── parser.py            ← J-word header parsing + decoder registry
│   │   └── messages/
│   │       ├── __init__.py      ← "How to add a message decoder"
│   │       ├── j2_2.py          ← J2.2 Air PPLI (stub)
│   │       ├── j3_2.py          ← J3.2 Air Track (stub)
│   │       └── j28_2.py         ← J28.2 Free Text (stub)
│   ├── tracks/
│   │   └── database.py          ← in-memory track store
│   ├── output/
│   │   ├── __init__.py          ← "How to add an output format"
│   │   ├── coords.py            ← decimal degrees ↔ military grid
│   │   ├── tacrep.py            ← 5-line AIROP TACREP
│   │   └── nineline.py          ← 9-line convenience format
│   ├── network/
│   │   ├── __init__.py          ← "How to add a network sink"
│   │   └── sink.py              ← TCP/UDP streaming sink
│   └── cli/
│       └── shell.py             ← interactive CLI shell
└── tests/
    └── __init__.py
```
