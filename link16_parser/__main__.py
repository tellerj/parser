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
import shutil
import sys
import threading

from link16_parser.cli import InteractiveShell
from link16_parser.core import EncapsulationDecoder, PacketSource
from link16_parser.encapsulation import ENCAP_CHOICES, build_decoder, register_encap_plugin
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
    net.add_argument(
        "--output-format",
        default="JSON",
        help="Output format for network sink (default: JSON). "
             "Must match a registered formatter name (e.g. JSON, CSV, TACREP, 9-LINE, BULLSEYE).",
    )

    p.add_argument(
        "--bullseye",
        default=None,
        metavar="LAT,LON",
        help="Set bullseye reference point as LAT,LON in decimal degrees "
             "(e.g. '37.0,-116.0'). Required to enable the BULLSEYE output format.",
    )

    p.add_argument(
        "--definitions-dir",
        default=None,
        help="Path to directory of JSON message definitions (MIL-STD-6016 field layouts)",
    )
    p.add_argument(
        "--encap-plugin",
        default=None,
        help="Dotted Python module path to an external JREAP-C decoder "
             "(e.g. 'jreap_decoder.decoder'). Also settable via "
             "LINK16_ENCAP_PLUGIN env var.",
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


def _warn_if_not_on_path() -> None:
    if shutil.which("link16-parser") is None:
        local_bin = os.path.join(os.path.expanduser("~"), ".local", "bin")
        border = "!" * 66
        print(f"""
{border}
  WARNING: 'link16-parser' IS NOT ON YOUR PATH

  You are running via 'python -m link16_parser', which works, but
  the 'link16-parser' command itself is not findable in your shell.

  It was most likely installed to: {local_bin}
  That directory is not in your current PATH.

  Fix it right now:
    export PATH="$HOME/.local/bin:$PATH"

  Fix it permanently (add to your shell config, then reload):
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    source ~/.bashrc

  Or re-run the install script, which handles this automatically:
    ./install.sh
{border}
""", file=sys.stderr)


def main() -> None:
    _warn_if_not_on_path()
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
    register_encap_plugin(cli_arg=args.encap_plugin)
    encap_decoder = build_decoder(args.encap)
    jword_parser = build_parser(definitions_dir=args.definitions_dir)
    track_db = TrackDatabase()
    track_db.start_aging()

    # Parse bullseye reference point
    bull_lat: float | None = None
    bull_lon: float | None = None
    if args.bullseye is not None:
        try:
            parts = args.bullseye.split(",")
            if len(parts) != 2:
                raise ValueError("expected LAT,LON")
            bull_lat, bull_lon = float(parts[0]), float(parts[1])
        except ValueError:
            parser.error(
                f"invalid --bullseye value '{args.bullseye}'. "
                f"Expected LAT,LON in decimal degrees (e.g. '37.0,-116.0')."
            )

    # Output formatters
    formatters = build_formatters(
        originator=args.originator,
        classification=args.classification,
        bullseye_lat=bull_lat,
        bullseye_lon=bull_lon,
    )

    # Network output sink (optional)
    network_sink: NetworkSink | None = None
    if args.output_host and args.output_port:
        sink_fmt_name = args.output_format.upper()
        sink_fmt = formatters.get(sink_fmt_name)
        if sink_fmt is None:
            if sink_fmt_name == "BULLSEYE":
                parser.error(
                    "BULLSEYE output format requires a reference point. "
                    "Add --bullseye LAT,LON (e.g. --bullseye 37.0,-116.0)."
                )
            parser.error(
                f"unknown output format '{sink_fmt_name}'. "
                f"Available: {', '.join(formatters.keys())}"
            )
        network_sink = NetworkSink(
            host=args.output_host,
            port=args.output_port,
            protocol=args.output_proto,
            formatter=sink_fmt,
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
        if sink_fmt_name == "BULLSEYE":
            bull_ref = getattr(sink_fmt, "reference", None)
            if bull_ref is not None:
                logger.info("Bullseye reference point: %.4f, %.4f", bull_ref[0], bull_ref[1])

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
                track_db.stop_aging()
                ingestion_thread.join(timeout=2.0)
                if network_sink is not None:
                    network_sink.stop()
            return

    # In pipe mode, redirect sys.stdin to /dev/tty so the shell's input()
    # call gets full readline support (history, tab completion, line editing).
    # PipeSource is already iterating on the original stdin buffer in the
    # ingestion thread — reassigning sys.stdin doesn't affect it.
    if tty_stream is not None:
        sys.stdin = tty_stream

    # Run interactive shell in foreground
    shell = InteractiveShell(
        track_db=track_db,
        formatters=formatters,
    )
    try:
        shell.run()
    finally:
        stop_event.set()
        track_db.stop_aging()
        ingestion_thread.join(timeout=2.0)
        if network_sink is not None:
            network_sink.stop()
        if tty_stream is not None:
            tty_stream.close()


if __name__ == "__main__":
    main()
