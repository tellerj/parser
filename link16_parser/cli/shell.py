"""Interactive CLI shell for querying tracks and producing reports.

Runs in the foreground while the ingestion thread updates the track
database in the background.
"""

from __future__ import annotations

import shlex
from collections.abc import MutableMapping
from typing import TextIO
import sys

from link16_parser.core.interfaces import OutputFormatter
from link16_parser.tracks.database import TrackDatabase


class InteractiveShell:
    """Interactive command shell for querying tracks and generating reports.

    Commands:
        list              — Show all currently tracked entities
        report <id>       — Generate report using the current default format
        tacrep <id>       — Generate TACREP for a track
        9line <id>        — Generate 9-line report for a track
        json <id>         — Generate JSON output for a track
        csv <id>          — Generate CSV output for a track
        bullseye set LAT,LON — Set bullseye reference point
        bullseye <id>     — Generate bullseye report for a track
        info <id>         — Show raw track data
        format [name]     — Switch default output format
        help              — Show available commands
        quit / exit       — Exit the shell
    """

    def __init__(
        self,
        track_db: TrackDatabase,
        formatters: MutableMapping[str, OutputFormatter],
        default_format: str = "TACREP",
        input_stream: TextIO | None = None,
        output_stream: TextIO | None = None,
    ) -> None:
        """Initialize the interactive shell.

        Args:
            track_db: The ``TrackDatabase`` to query.
            formatters: Map of format name (e.g. ``"TACREP"``) to
                ``OutputFormatter`` instance.
            default_format: Which formatter to use by default.
            input_stream: Override for stdin (useful for testing).
            output_stream: Override for stdout (useful for testing).
        """
        self._db = track_db
        self._formatters = formatters
        self._current_format = default_format
        self._input = input_stream or sys.stdin
        self._output = output_stream or sys.stdout
        self._running = False

    def run(self) -> None:
        """Start the interactive shell loop."""
        self._running = True
        self._print("Link 16 Parser — Type 'help' for commands.")
        self._print(f"Default format: {self._current_format}")
        self._print("")

        while self._running:
            try:
                self._output.write(">> ")
                self._output.flush()
                line = self._input.readline()
                if not line:
                    raise EOFError
                line = line.strip()
            except (EOFError, KeyboardInterrupt):
                self._print("\nExiting.")
                break

            if not line:
                continue

            try:
                parts = shlex.split(line)
            except ValueError:
                parts = line.split()

            cmd = parts[0].lower()
            args = parts[1:]

            handler = {
                "list": self._cmd_list,
                "ls": self._cmd_list,
                "report": self._cmd_report,
                "tacrep": self._cmd_tacrep,
                "9line": self._cmd_nineline,
                "json": self._cmd_json,
                "csv": self._cmd_csv,
                "bullseye": self._cmd_bullseye,
                "info": self._cmd_info,
                "format": self._cmd_format,
                "help": self._cmd_help,
                "quit": self._cmd_quit,
                "exit": self._cmd_quit,
            }.get(cmd)

            if handler is None:
                self._print(f"Unknown command: {cmd}. Type 'help' for commands.")
            else:
                handler(args)

    def _cmd_list(self, _args: list[str]) -> None:
        tracks = self._db.all_tracks()
        if not tracks:
            self._print("No tracks.")
            return

        self._print(f"{'STN':>7}  {'TN':>7}  {'CALLSIGN':<12} {'TYPE':<8} {'ID':<10} {'STATUS':<8} {'LAST UPDATE':<20} {'MSGS':>5}")
        self._print("-" * 85)
        for t in tracks:
            stn = str(t.stn)
            tn = t.track_number if t.track_number is not None else "-"
            cs = t.callsign if t.callsign is not None else "-"
            ptype = (t.platform.specific_type if t.platform and t.platform.specific_type else None) or \
                    (t.platform.generic_type if t.platform and t.platform.generic_type else None) or "-"
            ident = t.identity.value if t.identity else "-"
            status = t.status.value
            updated = t.last_updated.strftime("%d%H%MZ %Y-%m-%d") if t.last_updated else "-"
            msgs = str(t.message_count)
            self._print(f"{stn:>7}  {tn:>7}  {cs:<12} {ptype:<8} {ident:<10} {status:<8} {updated:<20} {msgs:>5}")

    def _cmd_report(self, args: list[str]) -> None:
        self._format_track(args, self._current_format)

    def _cmd_tacrep(self, args: list[str]) -> None:
        self._format_track(args, "TACREP")

    def _cmd_nineline(self, args: list[str]) -> None:
        self._format_track(args, "9-LINE")

    def _cmd_json(self, args: list[str]) -> None:
        self._format_track(args, "JSON")

    def _cmd_csv(self, args: list[str]) -> None:
        self._format_track(args, "CSV")

    def _cmd_bullseye(self, args: list[str]) -> None:
        # "bullseye set LAT,LON" — set or change the reference point
        if args and args[0].lower() == "set":
            self._bullseye_set(args[1:])
            return

        # No reference point configured yet — prompt the operator
        if "BULLSEYE" not in self._formatters:
            self._print("No bullseye reference point set.")
            self._print("  Usage: bullseye set LAT,LON   (e.g. bullseye set 37.0,-116.0)")
            return

        if not args:
            # No track specified — show current reference
            ref = getattr(self._formatters["BULLSEYE"], "reference", None)
            if ref is not None:
                self._print(f"  Bullseye reference: {ref[0]:.4f}, {ref[1]:.4f}")
            self._print("  Usage: bullseye <id>")
            return

        ref = getattr(self._formatters["BULLSEYE"], "reference", None)
        if ref is not None:
            self._print(f"  Bullseye reference: {ref[0]:.4f}, {ref[1]:.4f}")
        self._format_track(args, "BULLSEYE")

    def _bullseye_set(self, args: list[str]) -> None:
        from link16_parser.output.bullseye_format import BullseyeFormatter

        if not args:
            self._print("Usage: bullseye set LAT,LON   (e.g. bullseye set 37.0,-116.0)")
            return

        try:
            parts = args[0].split(",")
            if len(parts) != 2:
                raise ValueError("expected LAT,LON")
            lat, lon = float(parts[0]), float(parts[1])
        except ValueError:
            self._print(f"Invalid coordinates: '{args[0]}'")
            self._print("  Expected LAT,LON in decimal degrees (e.g. 37.0,-116.0)")
            return

        self._formatters["BULLSEYE"] = BullseyeFormatter(bull_lat=lat, bull_lon=lon)
        self._print(f"Bullseye reference set to: {lat:.4f}, {lon:.4f}")

    def _format_track(self, args: list[str], format_name: str) -> None:
        if not args:
            self._print(f"Usage: {format_name.lower()} <identifier>")
            return

        query = args[0]
        track = self._db.find(query)
        if track is None:
            self._print(f"No track found for '{query}'.")
            return

        formatter = self._formatters.get(format_name)
        if formatter is None:
            self._print(f"Unknown format: {format_name}")
            return

        self._print("")
        header_fn = getattr(formatter, "header", None)
        if header_fn is not None:
            self._print(header_fn())
        self._print(formatter.format(track))
        self._print("")

    def _cmd_info(self, args: list[str]) -> None:
        if not args:
            self._print("Usage: info <identifier>")
            return

        track = self._db.find(args[0])
        if track is None:
            self._print(f"No track found for '{args[0]}'.")
            return

        self._print(f"  STN:          {track.stn}")
        self._print(f"  Status:       {track.status.value}")
        self._print(f"  Track Number: {track.track_number if track.track_number is not None else 'N/A'}")
        self._print(f"  Callsign:     {track.callsign if track.callsign is not None else 'N/A'}")
        self._print(f"  Position:     {track.position if track.position is not None else 'N/A'}")
        self._print(f"  Identity:     {track.identity.value if track.identity else 'N/A'}")
        self._print(f"  Platform:     {track.platform if track.platform is not None else 'N/A'}")
        self._print(f"  Heading:      {track.heading_deg if track.heading_deg is not None else 'N/A'}")
        self._print(f"  Speed:        {track.speed_kph if track.speed_kph is not None else 'N/A'}")
        self._print(f"  Last Updated: {track.last_updated if track.last_updated is not None else 'N/A'}")
        self._print(f"  Messages:     {track.message_count}")
        if track.fields:
            for key, val in track.fields.items():
                self._print(f"  {key}:  {val}")

    def _cmd_format(self, args: list[str]) -> None:
        if not args:
            self._print(f"Current format: {self._current_format}")
            available = list(self._formatters.keys())
            if "BULLSEYE" not in available:
                available.append("BULLSEYE (requires: bullseye set LAT,LON)")
            self._print(f"Available: {', '.join(available)}")
            return

        name = args[0].upper()
        if name not in self._formatters:
            if name == "BULLSEYE":
                self._print("BULLSEYE format requires a reference point.")
                self._print("  Set one with: bullseye set LAT,LON")
            else:
                self._print(f"Unknown format: {name}. Available: {', '.join(self._formatters.keys())}")
            return

        self._current_format = name
        self._print(f"Default format set to: {name}")

    def _cmd_help(self, _args: list[str]) -> None:
        self._print("Commands:")
        self._print("  list              Show all tracked entities")
        self._print("  report <id>       Generate report using current format")
        self._print("  tacrep <id>       Generate TACREP for a track")
        self._print("  9line <id>        Generate 9-line report for a track")
        self._print("  json <id>         Generate JSON output for a track")
        self._print("  csv <id>          Generate CSV output for a track")
        self._print("  bullseye set LAT,LON  Set bullseye reference point")
        self._print("  bullseye <id>     Generate bullseye report for a track")
        self._print("  info <id>         Show raw track data")
        self._print("  format [name]     Show or switch default output format")
        self._print("  help              Show this help")
        self._print("  quit / exit       Exit")
        self._print("")
        self._print("Identifiers: STN (number), track number, or callsign")

    def _cmd_quit(self, _args: list[str]) -> None:
        self._running = False

    def _print(self, text: str) -> None:
        print(text, file=self._output)
