"""Interactive CLI shell for querying tracks and producing reports.

Runs in the foreground while the ingestion thread updates the track
database in the background.
"""

from __future__ import annotations

import shlex
from typing import TextIO
import sys

from link16_parser.core.interfaces import OutputFormatter
from link16_parser.tracks.database import TrackDatabase


class InteractiveShell:
    """Interactive command shell for querying tracks and generating reports.

    Commands:
        list              — Show all currently tracked entities
        tacrep <id>       — Generate TACREP for a track (by STN, callsign, or track#)
        9line <id>        — Generate 9-line report for a track
        info <id>         — Show raw track data
        format [name]     — Switch default output format (TACREP or 9-LINE)
        help              — Show available commands
        quit / exit       — Exit the shell
    """

    def __init__(
        self,
        track_db: TrackDatabase,
        formatters: dict[str, OutputFormatter],
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
                line = input(">> ").strip()
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
                "tacrep": self._cmd_tacrep,
                "9line": self._cmd_nineline,
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

        self._print(f"{'STN':>7}  {'TN':>7}  {'CALLSIGN':<12} {'TYPE':<8} {'ID':<10} {'LAST UPDATE':<20} {'MSGS':>5}")
        self._print("-" * 75)
        for t in tracks:
            stn = str(t.stn)
            tn = t.track_number or "-"
            cs = t.callsign or "-"
            ptype = (t.platform.specific_type or t.platform.generic_type) if t.platform else "-"
            ident = t.identity.value if t.identity else "-"
            updated = t.last_updated.strftime("%d%H%MZ %Y-%m-%d") if t.last_updated else "-"
            msgs = str(t.message_count)
            self._print(f"{stn:>7}  {tn:>7}  {cs:<12} {ptype:<8} {ident:<10} {updated:<20} {msgs:>5}")

    def _cmd_tacrep(self, args: list[str]) -> None:
        self._format_track(args, "TACREP")

    def _cmd_nineline(self, args: list[str]) -> None:
        self._format_track(args, "9-LINE")

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
        self._print(f"  Track Number: {track.track_number or 'N/A'}")
        self._print(f"  Callsign:     {track.callsign or 'N/A'}")
        self._print(f"  Position:     {track.position or 'N/A'}")
        self._print(f"  Identity:     {track.identity.value if track.identity else 'N/A'}")
        self._print(f"  Platform:     {track.platform or 'N/A'}")
        self._print(f"  Heading:      {track.heading_deg or 'N/A'}")
        self._print(f"  Speed:        {track.speed_kph or 'N/A'}")
        self._print(f"  Last Updated: {track.last_updated or 'N/A'}")
        self._print(f"  Messages:     {track.message_count}")

    def _cmd_format(self, args: list[str]) -> None:
        if not args:
            self._print(f"Current format: {self._current_format}")
            self._print(f"Available: {', '.join(self._formatters.keys())}")
            return

        name = args[0].upper()
        if name not in self._formatters:
            self._print(f"Unknown format: {name}. Available: {', '.join(self._formatters.keys())}")
            return

        self._current_format = name
        self._print(f"Default format set to: {name}")

    def _cmd_help(self, _args: list[str]) -> None:
        self._print("Commands:")
        self._print("  list              Show all tracked entities")
        self._print("  tacrep <id>       Generate TACREP for a track")
        self._print("  9line <id>        Generate 9-line report for a track")
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
