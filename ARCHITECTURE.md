# Architecture Overview

JREAP-C Parser is a modular pipeline that transforms raw PCAP network
captures containing Link 16 tactical data link traffic into formatted
tactical reports (TACREPs) and other structured output.

---

## Data Flow

The system is a linear pipeline. Each stage consumes one data type and
produces the next. No stage knows the internals of any other — they
communicate only through the shared types defined in `core/types.py`.

```mermaid
flowchart LR
    A["PCAP Source<br/>(file or stdin pipe)"] -->|"(timestamp, bytes)"| B["Encapsulation<br/>Decoder"]
    B -->|"RawJWord[]"| C["J-Word<br/>Parser"]
    C -->|"Link16Message[]"| D["Track<br/>Database"]
    D -->|"Track"| E["Output<br/>Formatter"]
    E -->|"string"| F["User"]
```

### Stage-by-stage

| Stage | Package | Input | Output | Notes |
|-------|---------|-------|--------|-------|
| **Ingestion** | `ingestion/` | PCAP bytes (file or pipe) | `(float, bytes)` tuples | Strips Ethernet/IP/UDP\|TCP headers |
| **Encapsulation** | `encapsulation/` | UDP/TCP payload bytes | `list[RawJWord]` | Pluggable: SIMPLE, SISO-J, JREAP-C, Auto |
| **J-Word Parsing** | `link16/` | `list[RawJWord]` | `list[Link16Message]` | Header parsing (public) + message decoding (needs MIL-STD-6016) |
| **Track DB** | `tracks/` | `Link16Message` | `Track` (stored) | In-memory, thread-safe, keyed by STN |
| **Formatting** | `output/` | `Track` | `str` | Pluggable: TACREP, 9-LINE, future formats |
| **CLI** | `cli/` | User commands | Formatted reports | Interactive shell, queries the Track DB |

---

## Module Map

```mermaid
graph TD
    subgraph core["core/"]
        types["types.py<br/>─────────<br/>Position, PlatformId,<br/>RawJWord, Link16Message,<br/>Track, Identity, WordFormat"]
        interfaces["interfaces.py<br/>─────────<br/>PacketSource,<br/>EncapsulationDecoder,<br/>MessageDecoder,<br/>OutputFormatter"]
    end

    subgraph ingestion["ingestion/"]
        pcap["pcap_reader.py<br/>─────────<br/>PcapFileSource<br/>PcapPipeSource"]
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
        db["database.py<br/>TrackDatabase"]
    end

    subgraph output["output/"]
        coords["coords.py<br/>coordinate conversion"]
        tacrep["tacrep.py<br/>TacrepFormatter"]
        nineline["nineline.py<br/>NineLineFormatter"]
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
    shell --> tacrep & nineline
    tacrep --> coords
    nineline --> coords
    main -.->|"wires"| pcap & detect & parser & db & shell
```

Items marked **⚠️** are stubs awaiting MIL-STD-6016 access.

---

## Threading Model

```mermaid
sequenceDiagram
    participant Main as main()
    participant Ingest as Ingestion Thread
    participant DB as TrackDatabase
    participant Shell as InteractiveShell

    Main->>Ingest: start (daemon thread)
    Main->>Shell: run (foreground)

    loop until source exhausted or stop_event
        Ingest->>Ingest: read packet from source
        Ingest->>Ingest: decode encapsulation → RawJWords
        Ingest->>Ingest: parse J-words → Link16Messages
        Ingest->>DB: update(message) [acquires lock]
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
```

Two threads, one shared resource (`TrackDatabase`), protected by a
single `threading.Lock`. The ingestion thread is the sole writer; the
CLI thread is the sole reader.

---

## The MIL-STD-6016 Boundary

This is the most important architectural line in the project. Everything
above it works with publicly documented specs. Everything below it
requires the restricted standard.

```mermaid
flowchart TB
    subgraph public["✅ PUBLIC — works today"]
        A["PCAP reader"]
        B["Encapsulation decoders<br/>(SIMPLE, DIS/SISO-J)"]
        C["J-word header parser<br/>(bits 0-12: word format,<br/>label, sublabel, MLI)"]
        D["Track database"]
        E["TACREP / 9-LINE formatters"]
        F["CLI shell"]
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
    style G fill:#2d3436,stroke:#e74c3c,color:#fff
```

**When MIL-STD-6016 becomes available**, the only files that change are
the message decoders in `link16/messages/` (e.g. `j2_2.py`, `j3_2.py`).
No other module is affected.

---

## Pluggable Extension Points

The architecture has three pluggable seams — places where you can add
new implementations without modifying existing code (beyond wiring).

| Extension Point | Protocol | Where to add | How to register |
|----------------|----------|--------------|-----------------|
| **Encapsulation format** | `EncapsulationDecoder` | `encapsulation/` | `detect.py` + `__main__.py` |
| **Message type decoder** | `MessageDecoder` | `link16/messages/` | `__main__.py` → `parser.register()` |
| **Output format** | `OutputFormatter` | `output/` | `__main__.py` → `formatters` dict |

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

---

## File Listing

```
jreap-c-parser/
├── ARCHITECTURE.md              ← you are here
├── pyproject.toml               ← package metadata, CLI entry point
├── jreap_parser/
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
│   └── cli/
│       └── shell.py             ← interactive CLI shell
└── tests/
    └── __init__.py
```
