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
import sys
import threading

from link16_parser.cli.shell import InteractiveShell
from link16_parser.core.interfaces import EncapsulationDecoder, PacketSource
from link16_parser.encapsulation.detect import AutoDecoder
from link16_parser.encapsulation.jreap_c import JreapCDecoder
from link16_parser.encapsulation.simple import SimpleDecoder
from link16_parser.encapsulation.siso_j import SisoJDecoder
from link16_parser.ingestion.pcap_reader import PcapFileSource, PcapPipeSource
from link16_parser.link16.messages.j2_2 import J22AirPpliDecoder
from link16_parser.link16.messages.j28_2 import J282FreeTextDecoder
from link16_parser.link16.messages.j3_2 import J32AirTrackDecoder
from link16_parser.link16.parser import JWordParser
from link16_parser.network.sink import NetworkSink
from link16_parser.output.nineline import NineLineFormatter
from link16_parser.output.tacrep import TacrepFormatter
from link16_parser.tracks.database import TrackDatabase

logger = logging.getLogger("link16_parser")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="link16-parser",
        description="Parse Link 16 PCAP traffic and produce TACREPs.",
    )
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", "-f", help="Path to a PCAP file")
    source.add_argument("--pipe", "-p", action="store_true", help="Read live PCAP from stdin")

    p.add_argument(
        "--encap", "-e",
        choices=["auto", "simple", "siso-j", "jreap-c"],
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


def build_encap_decoder(name: str) -> EncapsulationDecoder:
    """Instantiate the encapsulation decoder for the given format name.

    Args:
        name: One of ``"auto"``, ``"simple"``, ``"siso-j"``, ``"jreap-c"``.

    Returns:
        An ``EncapsulationDecoder`` instance.
    """
    return {
        "auto": AutoDecoder,
        "simple": SimpleDecoder,
        "siso-j": SisoJDecoder,
        "jreap-c": JreapCDecoder,
    }[name]()


def build_jword_parser() -> JWordParser:
    """Create a JWordParser with all available message decoders registered."""
    parser = JWordParser()
    parser.register(J22AirPpliDecoder())
    parser.register(J32AirTrackDecoder())
    parser.register(J282FreeTextDecoder())
    return parser


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

    except Exception:
        logger.exception("Ingestion error")

    logger.info("Ingestion complete: %d packets, %d messages", pkt_count, msg_count)


def main() -> None:
    args = build_parser().parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Build pipeline components
    if args.file:
        source: PacketSource = PcapFileSource(args.file, port_filter=args.port)
    else:
        source = PcapPipeSource(port_filter=args.port)

    encap_decoder = build_encap_decoder(args.encap)
    jword_parser = build_jword_parser()
    track_db = TrackDatabase()

    # Output formatters
    tacrep_fmt = TacrepFormatter(
        originator=args.originator,
        classification=args.classification,
    )
    formatters = {
        "TACREP": tacrep_fmt,
        "9-LINE": NineLineFormatter(),
    }

    # Network output sink (optional)
    network_sink: NetworkSink | None = None
    if args.output_host and args.output_port:
        network_sink = NetworkSink(
            host=args.output_host,
            port=args.output_port,
            protocol=args.output_proto,
            formatter=tacrep_fmt,
        )
        network_sink.start()
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

    # Run interactive shell in foreground
    shell = InteractiveShell(track_db=track_db, formatters=formatters)
    try:
        shell.run()
    finally:
        stop_event.set()
        ingestion_thread.join(timeout=2.0)
        if network_sink is not None:
            network_sink.stop()


if __name__ == "__main__":
    main()
