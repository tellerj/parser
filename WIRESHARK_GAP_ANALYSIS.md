# Research Findings: Wireshark vs link16-parser Gap Analysis

## Context

Before continuing development on the link16-parser project, we needed to answer:
does Wireshark/tshark already do what we're building? Could we just write
dissectors/protocol specs and be done?

## Research Summary

### What Wireshark's Link 16 dissector actually does

The `packet-link16.c` dissector was contributed in May 2014, based on a 10-week
Australian DSTO summer student project (DSTO-TN-1257, January 2014). It was
built using SISO-STD-002 (the simulation standard) and open literature only —
no MIL-STD-6016 access.

**It decodes ONLY the 13-bit J-word header:**
- Word Format (2 bits): Initial / Continuation / Extension
- Label (5 bits): message category (0-31)
- Sublabel (3 bits): message subtype (0-7)
- MLI (3 bits): Message Length Indicator

**It does NOT decode the 57-bit FWF payload.** No position, identity, speed,
heading, altitude, platform type, callsign, track number, or any other
tactical field.

The authors themselves said (Section 7, p.8):
> "The dissector presented in this work only decodes the label and sub-label
> fields. While this is sufficient for superficial analysis of Link 16
> networks, there are many fields within the J-series messages (such as track
> and coordinate numbers) that would make the dissector more useful."

This "further work" has **never been done** — the dissector is unchanged in
mainline Wireshark 12 years later. Only 5 `hf_` fields are registered. No one
has contributed FWF decoding.

### What Wireshark DOES cover well (transport/encapsulation)

| Layer | Wireshark dissector | Chains to link16? | Status |
|-------|-------------------|-------------------|--------|
| SIMPLE (STANAG 5602) | `packet-simple.c` | Yes — `call_dissector_with_data(link16_handle, ...)` | Full header decode |
| DIS/SISO-J (Signal PDU) | `packet-dis.c` | Yes — includes `packet-link16.h`, chains for TDL type Link 16 | Full PDU decode |
| JREAP-C (MIL-STD-3011) | `packet-jreap.c` | Exists but chaining status unclear | Header only |

### The tshark output proves the gap

From the paper's Appendix B, `tshark -r capture.pcap -V` on a J2.2 PPLI:
```
Link 16 J2.2I Air PPLI
    Word Format: Initial Word (0)
    Label: Precise Participant Location and Identificaton (2)
    Sublabel: 2
    Message Length Indicator: 2
```
That's it. No lat/lon, no identity, no speed. Just "this is a J2.2."

## Side-by-side comparison

| Capability | Wireshark (packet-link16.c) | link16-parser |
|------------|---------------------------|---------------|
| **PCAP reading** | libpcap + pcapng (via dumpcap) | libpcap only (pcapng stub) |
| **SIMPLE decode** | Full (packet-simple.c) | Full (simple.py) |
| **SISO-J/DIS decode** | Full (packet-dis.c) | Full (siso_j.py) |
| **JREAP-C decode** | Header only (packet-jreap.c) | Stub (plugin seam) |
| **J-word header** (13 bits) | Yes — label, sublabel, MLI | Yes — identical |
| **J-word FWF payload** (57 bits) | **No** | **Yes** — JSON-driven DefinitionDecoder |
| **Message type identification** | 53 label/sublabel pairs named | Same (from header) |
| **Field-level decode** (position, identity, etc.) | **None** | Full — via injected JSON definitions |
| **Track correlation by STN** | **None** (stateless per-packet) | Full — TrackDatabase with non-destructive merge |
| **Track aging (ACTIVE/STALE/DROPPED)** | **None** | Full — TTL-based with configurable timers |
| **Multi-message track assembly** | **None** | Full — J2.2 + J3.2 merged into single Track |
| **Tactical output formats** | N/A | TACREP, 9-LINE, JSON, CSV, Bullseye |
| **Interactive query** | Wireshark GUI / tshark filters | CLI shell (list, search, info, debug) |
| **Live streaming output** | N/A | NetworkSink (TCP/UDP with reconnect) |
| **Dependencies** | libpcap, GTK/Qt, ~2M lines of C | Python stdlib only |

## Conclusion

**The link16-parser project is NOT redundant.** Wireshark/tshark solves a
different problem (packet-level protocol identification) while link16-parser
solves the operational problem (what are the tracks doing, where are they,
who are they).

The overlap is narrow — both parse PCAP frames, both decode SIMPLE/SISO-J
encapsulation headers, and both extract the 13-bit J-word header. But that's
the easy part. The hard and valuable part — decoding the 57-bit FWF payload
into tactical fields, correlating messages into tracks over time, aging tracks,
and producing formatted reports — exists only in link16-parser.

### Could we use tshark as a front-end?

Theoretically: `tshark -T json | link16-parser --from-json`. But this would:
- Add a runtime dependency on Wireshark being installed
- Give us nothing we don't already have (our SIMPLE/SISO-J decoders work)
- Not help with the hard part (FWF decoding, track correlation)
- Add complexity for zero functional gain

**Not worth it.** The architecture is sound as-is.

### What about writing a Wireshark Lua plugin for FWF decoding?

This would be the "give back to Wireshark" approach — write a Lua post-dissector
that decodes J-series FWF payloads and register fields with Wireshark's filter
system. But:
- It would only solve packet-level field display, not track correlation
- Lua dissectors are slow for high-volume PCAPs
- The JSON definition files from link16-parser could potentially drive it
- It's a nice-to-have contribution, not a replacement for this project

## Sources

- [packet-link16.c](https://github.com/wireshark/wireshark/blob/master/epan/dissectors/packet-link16.c) — 5 registered fields, header-only parsing
- [packet-link16.h](https://github.com/wireshark/wireshark/blob/master/epan/dissectors/packet-link16.h) — Link16State struct: label, sublabel, extension
- [DSTO-TN-1257 (PDF)](https://willrobertson.id.au/resources/wireshark/DSTO-TN-1257.pdf) — "only decodes the label and sub-label fields"
- [Wireshark commit (May 2014)](https://lists.wireshark.org/archives/wireshark-commits/201405/msg00159.html)
- [packet-simple.c chains to link16](https://raw.githubusercontent.com/wireshark/wireshark/master/epan/dissectors/packet-simple.c) — confirmed via `call_dissector_with_data`
