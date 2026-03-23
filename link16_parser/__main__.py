"""Main entry point: wires all modules together and runs the tool.

Usage:
    # From a PCAP file:
    python -m link16_parser --file capture.pcap

    # From a live pipe:
    tcpdump -w - | python -m link16_parser --pipe

    # Specify encapsulation format (default: auto-detect):
    python -m link16_parser --file capture.pcap --encap simple

    # Filter ingestion to a specific port:
    python -m link16_parser --file capture.pcap --port 4444

    # Stream formatted output to a remote endpoint:
    python -m link16_parser --file capture.pcap --output-host 192.168.1.10 --output-port 9000
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading

from link16_parser.cli import InteractiveShell
from link16_parser.core import EncapsulationDecoder, PacketSource
from link16_parser.encapsulation import ENCAP_CHOICES, build_decoder
from link16_parser.ingestion import build_source
from link16_parser.link16 import JWordParser, build_parser
from link16_parser.network import NetworkSink
from link16_parser.output import build_formatters
from link16_parser.tracks import TrackDatabase

logger = logging.getLogger("link16_parser")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="link16-parser",
        description="Parse Link 16 tactical data link traffic from PCAP captures and produce formatted reports (TACREPs, 9-LINEs).",
        epilog="""\
file examples (all options work with both .pcap and .pcapng files):
  %(prog)s --file capture.pcap
  %(prog)s --file capture.pcapng
  %(prog)s --file capture.pcap --port 4444
  %(prog)s --file capture.pcap --encap simple
  %(prog)s --file capture.pcapng --encap siso-j
  %(prog)s --file capture.pcap --encap jreap-c
  %(prog)s --file capture.pcapng --originator "CTF124" --classification SECRET
  %(prog)s --file capture.pcap --output-host 192.168.1.10 --output-port 9000
  %(prog)s --file capture.pcapng --output-host 10.0.0.5 --output-port 5000 --output-proto udp
  %(prog)s --file capture.pcap --port 4444 --encap simple --verbose

pipe examples (live monitoring):
  tcpdump -i eth0 -w - | %(prog)s --pipe
  tcpdump -i eth0 -w - udp port 4444 | %(prog)s --pipe
  tshark -i eth0 -w - | %(prog)s --pipe
  tshark -i eth0 -w - -f "udp port 4444" | %(prog)s --pipe
  dumpcap -i eth0 -w - | %(prog)s --pipe
  socat UDP-RECV:4444 - | tcpdump -r - -w - | %(prog)s --pipe
  ssh remote-host "tcpdump -i eth0 -w -" | %(prog)s --pipe
  cat capture.pcap | %(prog)s --pipe

note:
  This tool does not capture packets from the network — it reads
  captures produced by other tools (tcpdump, tshark, dumpcap, etc.).
  For live monitoring, pipe from a capture tool as shown above.

  Supported capture formats: libpcap (.pcap), pcapng (.pcapng).
  Supported encapsulations: SIMPLE (STANAG 5602), DIS/SISO-J, JREAP-C.
  Format and encapsulation are auto-detected by default.

  Once running, an interactive shell provides commands for querying
  tracks and generating reports. Type 'help' at the >> prompt.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", "-f", help="Path to a PCAP file")
    source.add_argument("--pipe", "-p", action="store_true", help="Read live PCAP from stdin")

    p.add_argument(
        "--encap", "-e",
        choices=ENCAP_CHOICES,
        default="auto",
        help="Encapsulation format (default: auto-detect)",
    )
    p.add_argument(
        "--port",
        type=int,
        default=None,
        help="Only process packets on this port (src or dst). Default: all ports.",
    )

    net = p.add_argument_group("network output", "Stream formatted output to a remote endpoint")
    net.add_argument("--output-host", default=None, help="Remote host for network output sink")
    net.add_argument("--output-port", type=int, default=None, help="Remote port for network output sink")
    net.add_argument(
        "--output-proto",
        choices=["tcp", "udp"],
        default="tcp",
        help="Transport protocol for network output (default: tcp)",
    )

    p.add_argument("--originator", default="L16-PARSER", help="TACREP originator field")
    p.add_argument("--classification", default="UNCLAS", help="Classification marking")
    p.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    return p


def ingestion_loop(
    source: PacketSource,
    encap_decoder: EncapsulationDecoder,
    jword_parser: JWordParser,
    track_db: TrackDatabase,
    stop_event: threading.Event,
) -> None:
    """Background thread: read packets, decode, parse, update track DB.

    Runs until the source is exhausted or ``stop_event`` is set.
    Exceptions are logged but do not propagate (daemon thread).

    Args:
        source: The PCAP packet source (file or pipe).
        encap_decoder: Strips encapsulation, produces ``RawJWord`` objects.
        jword_parser: Parses J-word headers and dispatches to decoders.
        track_db: The shared track database to update.
        stop_event: Set this to signal the loop to exit.
    """
    msg_count = 0
    pkt_count = 0

    try:
        for pcap_ts, payload in source.packets():
            if stop_event.is_set():
                break

            pkt_count += 1
            raw_words = encap_decoder.decode(payload, pcap_ts)
            if not raw_words:
                continue

            messages = jword_parser.parse(raw_words)
            for msg in messages:
                track_db.update(msg)
                msg_count += 1

    except ValueError as exc:
        # PCAP format errors — bad magic, wrong link-layer type, etc.
        logger.error("Failed to read PCAP input: %s", exc)
    except OSError as exc:
        logger.error(
            "I/O error reading PCAP source after %d packets: %s",
            pkt_count, exc,
        )
    except Exception:
        logger.exception(
            "Unexpected error during ingestion after %d packets, %d messages",
            pkt_count, msg_count,
        )

    logger.info("Ingestion complete: %d packets, %d messages", pkt_count, msg_count)


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # --- Argument validation ---
    if args.file and not os.path.isfile(args.file):
        parser.error(f"file not found: {args.file}")

    if (args.output_host is None) != (args.output_port is None):
        parser.error("--output-host and --output-port must be specified together")

    # Build pipeline components
    source = build_source(file=args.file, pipe=args.pipe, port_filter=args.port)
    encap_decoder = build_decoder(args.encap)
    jword_parser = build_parser()
    track_db = TrackDatabase()

    # Output formatters
    formatters = build_formatters(
        originator=args.originator,
        classification=args.classification,
    )

    # Network output sink (optional)
    network_sink: NetworkSink | None = None
    if args.output_host and args.output_port:
        # NetworkSink needs a specific formatter, not the dict
        tacrep_fmt = formatters.get("TACREP")
        network_sink = NetworkSink(
            host=args.output_host,
            port=args.output_port,
            protocol=args.output_proto,
            formatter=tacrep_fmt,
        )
        try:
            network_sink.start()
        except OSError as exc:
            logger.error(
                "Cannot start network sink (%s:%d over %s): %s. "
                "Check that the remote endpoint is reachable.",
                args.output_host, args.output_port, args.output_proto, exc,
            )
            sys.exit(1)
        track_db.on_update(network_sink.on_track_update)
        logger.info("Network sink active: %s", network_sink.name)

    # Start ingestion in background thread
    stop_event = threading.Event()
    ingestion_thread = threading.Thread(
        target=ingestion_loop,
        args=(source, encap_decoder, jword_parser, track_db, stop_event),
        daemon=True,
        name="ingestion",
    )
    ingestion_thread.start()

    # In pipe mode, stdin is consumed by PipeSource — read shell input
    # from the controlling terminal instead.
    tty_stream = None
    if args.pipe:
        try:
            tty_stream = open("/dev/tty", "r")
        except OSError:
            # No controlling terminal (cron, Docker, CI, etc.).
            # Run headless: ingestion only, wait for completion or Ctrl-C.
            logger.info("No controlling terminal — running in headless mode")
            try:
                ingestion_thread.join()
            except KeyboardInterrupt:
                pass
            finally:
                stop_event.set()
                ingestion_thread.join(timeout=2.0)
                if network_sink is not None:
                    network_sink.stop()
            return

    # Run interactive shell in foreground
    shell = InteractiveShell(
        track_db=track_db,
        formatters=formatters,
        input_stream=tty_stream,
    )
    try:
        shell.run()
    finally:
        stop_event.set()
        ingestion_thread.join(timeout=2.0)
        if network_sink is not None:
            network_sink.stop()
        if tty_stream is not None:
            tty_stream.close()


if __name__ == "__main__":
    main()
