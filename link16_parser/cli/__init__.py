"""Interactive CLI shell for querying tracks and producing reports.

Commands: list, search, status, report, tacrep, 9line, json, csv,
bullseye, info, export, config, debug, format, help, quit/exit.

Supports readline history, tab completion, and pipe-mode operation.
See ``shell.py`` for full documentation.
"""

from link16_parser.cli.shell import InteractiveShell

__all__ = ["InteractiveShell"]
