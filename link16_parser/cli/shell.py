"""Interactive CLI shell for querying tracks and producing reports.

Runs in the foreground while the ingestion thread updates the track
database in the background.
"""

from __future__ import annotations

import os
import shlex
import sys
from collections import Counter
from collections.abc import Callable, MutableMapping
from typing import TextIO

from link16_parser.core.interfaces import OutputFormatter
from link16_parser.core.types import Link16Message, Track, TrackStatus
from link16_parser.tracks.database import TrackDatabase

try:
    import readline as _readline  # enables line editing, history, and tab completion
except ImportError:
    _readline = None  # type: ignore[assignment]  # Windows or minimal Python

# Common format name typos that should resolve to the canonical key.
_FORMAT_ALIASES: dict[str, str] = {
    "9LINE": "9-LINE",
    "NINELINE": "9-LINE",
}

_CONFIG_KEYS = ["format", "originator", "classification", "bullseye", "stale-ttl", "drop-ttl"]


class InteractiveShell:
    """Interactive command shell for querying tracks and generating reports.

    Commands:
        list / ls         — Show all currently tracked entities
        search <query>    — Filter tracks by identity, type, status, or callsign
        status            — Show operational summary (track counts, identities)
        report <id>       — Generate report using the current default format
        tacrep <id>       — Generate TACREP for a track
        9line <id>        — Generate 9-line report for a track
        json <id>         — Generate JSON output for a track
        csv <id>          — Generate CSV output for a track
        bullseye set LAT,LON — Set bullseye reference point
        bullseye <id>     — Generate bullseye report for a track
        info <id>         — Show raw track data
        export <fmt> <file> [query] — Export tracks to a file
        config [key] [value] — Show or change runtime settings
        debug <id>        — Show message history for a track
        format [name]     — Switch default output format
        help              — Show available commands
        quit / exit       — Exit the shell
    """

    _COMMANDS = [
        "list", "ls", "search", "status", "report", "tacrep", "9line",
        "json", "csv", "bullseye", "info", "export", "config", "debug",
        "format", "help", "quit", "exit",
    ]

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
        self._handlers: dict[str, Callable[[list[str]], None]] = {
            "list": self._cmd_list,
            "ls": self._cmd_list,
            "search": self._cmd_search,
            "status": self._cmd_status,
            "report": self._cmd_report,
            "tacrep": self._cmd_tacrep,
            "9line": self._cmd_nineline,
            "json": self._cmd_json,
            "csv": self._cmd_csv,
            "bullseye": self._cmd_bullseye,
            "info": self._cmd_info,
            "export": self._cmd_export,
            "config": self._cmd_config,
            "debug": self._cmd_debug,
            "format": self._cmd_format,
            "help": self._cmd_help,
            "quit": self._cmd_quit,
            "exit": self._cmd_quit,
        }

    def _complete(self, text: str, state: int) -> str | None:
        """Readline tab-completion callback."""
        if _readline is None:
            return None

        buf = _readline.get_line_buffer().lstrip()
        words = buf.split()

        if len(words) <= 1:
            # Completing the command name
            candidates = [c for c in self._COMMANDS if c.startswith(text)]
        elif words[0] == "format":
            names = list(self._formatters.keys())
            candidates = [n for n in names if n.lower().startswith(text.lower())]
        elif words[0] == "export" and len(words) == 2:
            # Completing format name as first arg to export
            names = list(self._formatters.keys())
            candidates = [n for n in names if n.lower().startswith(text.lower())]
        elif words[0] == "config" and len(words) == 2:
            candidates = [k for k in _CONFIG_KEYS if k.startswith(text.lower())]
        elif words[0] in ("list", "ls") and len(words) == 2:
            candidates = ["all"] if "all".startswith(text.lower()) else []
        else:
            candidates = []

        if state < len(candidates):
            return candidates[state] + " "
        return None

    def run(self) -> None:
        """Start the interactive shell loop."""
        self._running = True

        # Install tab completion when on a real terminal
        if self._input is sys.stdin and _readline is not None:
            _readline.set_completer(self._complete)
            _readline.parse_and_bind("tab: complete")

        self._print("Link 16 Parser — Type 'help' for commands.")
        self._print(f"Default format: {self._current_format}")
        self._print("")

        while self._running:
            try:
                if self._input is sys.stdin:
                    # Real terminal — use input() for readline history/editing
                    line = input(">> ")
                else:
                    # Injected stream (testing) — use raw readline
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
            except ValueError as exc:
                self._print(f"Parse error: {exc}. Check for unmatched quotes.")
                continue

            cmd = parts[0].lower()
            args = parts[1:]

            handler = self._handlers.get(cmd)

            if handler is None:
                self._print(f"Unknown command: {cmd}. Type 'help' for commands.")
            else:
                handler(args)

    # ------------------------------------------------------------------
    # Track listing & search
    # ------------------------------------------------------------------

    def _cmd_list(self, args: list[str]) -> None:
        show_all = args and args[0].lower() == "all"
        if args and not show_all:
            self._print("Hint: 'list' accepts only 'all' (use 'list all' to include dropped). Did you mean 'search'?")
        tracks = self._db.all_tracks()
        if not show_all:
            tracks = [t for t in tracks if t.status != TrackStatus.DROPPED]
        if not tracks:
            self._print("No tracks.")
            return
        self._render_track_table(tracks)

    def _cmd_search(self, args: list[str]) -> None:
        if not args:
            self._print("Usage: search <query>")
            self._print("  Matches against identity, platform type, status, or callsign.")
            return

        raw_query = " ".join(args)
        query = raw_query.upper()
        tracks = self._db.all_tracks()
        matches = [t for t in tracks if self._track_matches(t, query)]

        if not matches:
            self._print(f"No tracks matching '{raw_query}'.")
            return
        self._render_track_table(matches)

    @staticmethod
    def _track_matches(track: Track, query: str) -> bool:
        """Check if a track matches a search query (case-insensitive)."""
        if track.identity and query in track.identity.value.upper():
            return True
        if track.platform:
            if track.platform.specific_type and query in track.platform.specific_type.upper():
                return True
            if track.platform.generic_type and query in track.platform.generic_type.upper():
                return True
        if query in track.status.value.upper():
            return True
        if track.callsign and query in track.callsign.upper():
            return True
        return False

    def _render_track_table(self, tracks: list[Track]) -> None:
        """Render a tabular track listing with header, rows, and count."""
        self._print(
            f"{'STN':>7}  {'TN':>7}  {'CALLSIGN':<12} {'TYPE':<8} "
            f"{'ID':<10} {'STATUS':<8} {'LAST UPDATE':<20} {'MSGS':>5}"
        )
        self._print("-" * 85)
        for t in tracks:
            stn = str(t.stn)
            tn = t.track_number if t.track_number is not None else "-"
            cs = t.callsign if t.callsign is not None else "-"
            if len(cs) > 12:
                cs = cs[:11] + "~"
            ptype = (
                (t.platform.specific_type if t.platform and t.platform.specific_type else None)
                or (t.platform.generic_type if t.platform and t.platform.generic_type else None)
                or "-"
            )
            if len(ptype) > 8:
                ptype = ptype[:7] + "~"
            ident = t.identity.value if t.identity else "-"
            status = t.status.value
            updated = t.last_updated.strftime("%d%H%MZ %Y-%m-%d") if t.last_updated else "-"
            msgs = str(t.message_count)
            self._print(
                f"{stn:>7}  {tn:>7}  {cs:<12} {ptype:<8} "
                f"{ident:<10} {status:<8} {updated:<20} {msgs:>5}"
            )
        self._print(f"--- {len(tracks)} track{'s' if len(tracks) != 1 else ''} ---")

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def _cmd_status(self, args: list[str]) -> None:
        if args:
            self._print("Hint: 'status' takes no arguments.")

        tracks = self._db.all_tracks()
        total = len(tracks)

        status_counts: Counter[str] = Counter()
        identity_counts: Counter[str] = Counter()
        for t in tracks:
            status_counts[t.status.value] += 1
            identity_counts[t.identity.value if t.identity else "UNKNOWN"] += 1

        # Track summary
        status_parts = [f"{count} {name.lower()}" for name, count in status_counts.most_common()]
        self._print(f"  Tracks:   {total} ({', '.join(status_parts)})" if status_parts else f"  Tracks:   {total}")

        # Identity breakdown
        id_parts = [f"{count} {name.lower()}" for name, count in identity_counts.most_common()]
        if id_parts:
            self._print(f"  Identity: {', '.join(id_parts)}")

        # Current format
        self._print(f"  Format:   {self._current_format}")

        # Bullseye reference (if set)
        if "BULLSEYE" in self._formatters:
            ref = getattr(self._formatters["BULLSEYE"], "reference", None)
            if ref is not None:
                self._print(f"  Bullseye: {ref[0]:.4f}, {ref[1]:.4f}")

    # ------------------------------------------------------------------
    # Format commands (report, tacrep, 9line, json, csv, bullseye)
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Info & debug
    # ------------------------------------------------------------------

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

    def _cmd_debug(self, args: list[str]) -> None:
        if not args:
            self._print("Usage: debug <identifier>")
            return

        track = self._db.find(args[0])
        if track is None:
            self._print(f"No track found for '{args[0]}'.")
            return

        history = self._db.message_history(track.stn)

        # Summary
        self._print(f"  STN:          {track.stn} (0o{track.stn:05o})")
        self._print(f"  Status:       {track.status.value}")
        if track.track_number is not None:
            self._print(f"  Track Number: {track.track_number}")
        self._print(f"  Messages:     {track.message_count} (showing last {len(history)})")

        # Message type breakdown from history
        if history:
            type_counts: Counter[str] = Counter(m.msg_type for m in history)
            type_parts = [f"{name} (\u00d7{count})" for name, count in type_counts.most_common()]
            self._print(f"  Msg Types:    {', '.join(type_parts)}")

        # Recent messages (newest first)
        if history:
            self._print("")
            self._print("  Recent messages (newest first):")
            for msg in reversed(history):
                self._print(f"    {self._format_debug_message(msg)}")

    @staticmethod
    def _format_debug_message(msg: Link16Message) -> str:
        """Format a single message as a compact one-line debug summary."""
        ts = msg.timestamp.strftime("%H:%M:%SZ")
        parts = [f"[{ts}]", msg.msg_type]
        if msg.position is not None:
            pos = f"pos={msg.position.lat:.4f},{msg.position.lon:.4f}"
            if msg.position.alt_m is not None:
                pos += f" alt={msg.position.alt_m:.0f}m"
            parts.append(pos)
        if msg.identity is not None:
            parts.append(f"id={msg.identity.value}")
        if msg.platform is not None:
            ptype = msg.platform.specific_type or msg.platform.generic_type
            if ptype:
                parts.append(f"type={ptype}")
        if msg.speed_kph is not None:
            parts.append(f"spd={msg.speed_kph:.0f}kph")
        if msg.heading_deg is not None:
            parts.append(f"hdg={msg.heading_deg:.0f}")
        if msg.callsign is not None:
            parts.append(f"cs={msg.callsign}")
        if msg.fields:
            for key, val in msg.fields.items():
                if isinstance(val, (str, int, float)):
                    parts.append(f"{key}={val}")
        return " ".join(parts)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _cmd_export(self, args: list[str]) -> None:
        if len(args) < 2:
            self._print("Usage: export <format> <file> [query]")
            self._print("  Exports all tracks (or matching tracks if query given) to a file.")
            return

        fmt_name = args[0].upper()
        fmt_name = _FORMAT_ALIASES.get(fmt_name, fmt_name)
        filepath = args[1]
        query = args[2].upper() if len(args) > 2 else None

        formatter = self._formatters.get(fmt_name)
        if formatter is None:
            self._print(f"Unknown format: {fmt_name}. Available: {', '.join(self._formatters.keys())}")
            return

        tracks = self._db.all_tracks()
        if query is not None:
            tracks = [t for t in tracks if self._track_matches(t, query)]

        existed = os.path.exists(filepath)
        try:
            with open(filepath, "w") as f:
                header_fn = getattr(formatter, "header", None)
                if header_fn is not None:
                    f.write(header_fn() + "\n")
                for t in tracks:
                    f.write(formatter.format(t) + "\n")
        except OSError as exc:
            self._print(f"Error writing to '{filepath}': {exc}")
            return

        overwrite_note = " (overwritten)" if existed else ""
        self._print(f"Exported {len(tracks)} track{'s' if len(tracks) != 1 else ''} to {filepath}{overwrite_note}")

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def _cmd_config(self, args: list[str]) -> None:
        if not args:
            self._print(f"  format:         {self._current_format}")
            tacrep = self._formatters.get("TACREP")
            if tacrep is not None:
                originator = getattr(tacrep, "originator", None)
                classification = getattr(tacrep, "classification", None)
                if originator is not None:
                    self._print(f"  originator:     {originator}")
                if classification is not None:
                    self._print(f"  classification: {classification}")
            self._print(f"  stale-ttl:      {self._db.stale_ttl:.0f}s")
            self._print(f"  drop-ttl:       {self._db.drop_ttl:.0f}s")
            if "BULLSEYE" in self._formatters:
                ref = getattr(self._formatters["BULLSEYE"], "reference", None)
                if ref is not None:
                    self._print(f"  bullseye:       {ref[0]:.4f}, {ref[1]:.4f}")
            return

        key = args[0].lower()
        if key == "format":
            self._cmd_format(args[1:])
        elif key == "bullseye":
            self._bullseye_set(args[1:])
        elif key == "originator":
            if len(args) < 2:
                self._print("Usage: config originator <value>")
                return
            tacrep = self._formatters.get("TACREP")
            if tacrep is None:
                self._print("TACREP formatter not available.")
                return
            tacrep.originator = args[1]  # type: ignore[union-attr]
            self._print(f"  originator set to: {args[1]}")
        elif key == "classification":
            if len(args) < 2:
                self._print("Usage: config classification <value>")
                return
            tacrep = self._formatters.get("TACREP")
            if tacrep is None:
                self._print("TACREP formatter not available.")
                return
            tacrep.classification = args[1]  # type: ignore[union-attr]
            self._print(f"  classification set to: {args[1]}")
        elif key == "stale-ttl":
            if len(args) < 2:
                self._print("Usage: config stale-ttl <seconds>")
                return
            try:
                self._db.stale_ttl = float(args[1])
                self._print(f"  stale-ttl set to: {self._db.stale_ttl:.0f}s")
            except ValueError:
                self._print(f"Invalid value: {args[1]}")
        elif key == "drop-ttl":
            if len(args) < 2:
                self._print("Usage: config drop-ttl <seconds>")
                return
            try:
                self._db.drop_ttl = float(args[1])
                self._print(f"  drop-ttl set to: {self._db.drop_ttl:.0f}s")
            except ValueError:
                self._print(f"Invalid value: {args[1]}")
        else:
            self._print(f"Unknown config key: {key}")
            self._print(f"  Available: {', '.join(_CONFIG_KEYS)}")

    # ------------------------------------------------------------------
    # Format switching
    # ------------------------------------------------------------------

    def _cmd_format(self, args: list[str]) -> None:
        if not args:
            self._print(f"Current format: {self._current_format}")
            available = list(self._formatters.keys())
            if "BULLSEYE" not in available:
                available.append("BULLSEYE (requires: bullseye set LAT,LON)")
            self._print(f"Available: {', '.join(available)}")
            return

        name = args[0].upper()
        name = _FORMAT_ALIASES.get(name, name)
        if name not in self._formatters:
            if name == "BULLSEYE":
                self._print("BULLSEYE format requires a reference point.")
                self._print("  Set one with: bullseye set LAT,LON")
            else:
                self._print(f"Unknown format: {name}. Available: {', '.join(self._formatters.keys())}")
            return

        self._current_format = name
        self._print(f"Default format set to: {name}")

    # ------------------------------------------------------------------
    # Help & quit
    # ------------------------------------------------------------------

    def _cmd_help(self, _args: list[str]) -> None:
        fmt_names = ", ".join(self._formatters.keys())
        self._print("Commands:")
        self._print("  list [all]        Show tracked entities (all = include dropped)")
        self._print("  search <query>    Filter tracks by identity, type, status, or callsign")
        self._print("  status            Show operational summary")
        self._print("  report <id>       Generate report using current format")
        self._print("  tacrep <id>       Generate TACREP for a track")
        self._print("  9line <id>        Generate 9-line report for a track")
        self._print("  json <id>         Generate JSON output for a track")
        self._print("  csv <id>          Generate CSV output for a track")
        self._print("  bullseye set LAT,LON  Set bullseye reference point")
        self._print("  bullseye <id>     Generate bullseye report for a track")
        self._print("  info <id>         Show raw track data")
        self._print("  export <fmt> <file> [query]  Export tracks to a file")
        self._print("  config [key] [value]  Show or change settings")
        self._print("  debug <id>        Show message history for a track")
        self._print(f"  format [name]     Show or switch format (available: {fmt_names})")
        self._print("  help              Show this help")
        self._print("  quit / exit       Exit")
        self._print("")
        self._print("Identifiers: STN (5-digit = octal, else decimal), track number, or callsign (case-insensitive)")

    def _cmd_quit(self, _args: list[str]) -> None:
        self._print("Exiting.")
        self._running = False

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _print(self, text: str) -> None:
        try:
            print(text, file=self._output)
        except BrokenPipeError:
            self._running = False
