"""Network output sink — streams formatted track updates over TCP or UDP.

Connects to a remote endpoint and pushes formatted reports as tracks
are updated. Uses a background sender thread with a queue to avoid
blocking the ingestion pipeline.
"""

from __future__ import annotations

import logging
import queue
import socket
import threading
import time

from link16_parser.core.interfaces import OutputFormatter
from link16_parser.core.types import Link16Message, Track

logger = logging.getLogger(__name__)

# Only log queue-full warnings at most once per this many seconds
_QUEUE_FULL_LOG_INTERVAL = 10.0

# Reconnection backoff parameters (seconds)
_RECONNECT_INITIAL = 1.0
_RECONNECT_MAX = 30.0
_RECONNECT_MULTIPLIER = 2.0


class NetworkSink:
    """Streams formatted track reports to a TCP or UDP endpoint.

    Each track update is formatted using the configured ``OutputFormatter``
    and sent as a newline-terminated message to the remote endpoint.

    Uses a non-blocking queue + background sender thread so that the
    ``on_track_update()`` callback (called inside the DB lock) returns
    immediately without waiting on network I/O.

    Args:
        host: Remote hostname or IP address.
        port: Remote port number.
        protocol: ``"tcp"`` or ``"udp"``.
        formatter: The ``OutputFormatter`` to use for serializing tracks.
            Selected via ``--output-format`` (default: JSON).
        queue_size: Maximum number of pending messages before dropping.
            ``0`` means unlimited (not recommended for production).
    """

    def __init__(
        self,
        host: str,
        port: int,
        protocol: str = "tcp",
        formatter: OutputFormatter | None = None,
        queue_size: int = 1000,
    ) -> None:
        self._host = host
        self._port = port
        self._protocol = protocol.lower()
        self._formatter = formatter
        self._queue: queue.Queue[tuple[Track, Link16Message | None] | None] = queue.Queue(maxsize=queue_size)
        self._socket: socket.socket | None = None
        self._sender_thread: threading.Thread | None = None
        self._running = False
        self._drop_count = 0
        self._last_drop_log: float = 0.0

    @property
    def name(self) -> str:
        return f"{self._protocol.upper()}:{self._host}:{self._port}"

    def start(self) -> None:
        """Open the socket connection and start the sender thread.

        Raises:
            ConnectionRefusedError: If TCP connection cannot be established.
            OSError: For other socket errors.
        """
        if self._protocol == "tcp":
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                self._socket.connect((self._host, self._port))
            except ConnectionRefusedError:
                raise ConnectionRefusedError(
                    f"Cannot connect to {self.name} — is the remote endpoint listening? "
                    f"Check that --output-host and --output-port are correct."
                )
            except OSError as exc:
                raise OSError(
                    f"Cannot connect to {self.name}: {exc}. "
                    f"Check that the host is reachable and the port is correct."
                ) from exc
            logger.info("Connected to %s", self.name)
        elif self._protocol == "udp":
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            logger.info("UDP sink ready: %s", self.name)
        else:
            raise ValueError(
                f"Unsupported protocol: '{self._protocol}'. Use 'tcp' or 'udp'."
            )

        self._running = True
        self._sender_thread = threading.Thread(
            target=self._sender_loop,
            daemon=True,
            name=f"network-sink-{self.name}",
        )
        self._sender_thread.start()

    def stop(self) -> None:
        """Signal the sender thread to exit and close the socket.

        Idempotent — safe to call multiple times.
        """
        self._running = False

        # Send poison pill to unblock the sender thread
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass

        if self._sender_thread is not None:
            self._sender_thread.join(timeout=2.0)
            self._sender_thread = None

        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None
            logger.info("Closed %s", self.name)

        if self._drop_count > 0:
            logger.warning(
                "Network sink %s dropped %d updates total during this session",
                self.name, self._drop_count,
            )

    def on_track_update(self, track: Track, message: Link16Message | None) -> None:
        """Enqueue a track snapshot for network delivery.

        Called inside the ``TrackDatabase`` lock. Snapshots the track
        and enqueues without blocking — formatting is deferred to the
        sender thread. If the queue is full, the update is dropped with
        a throttled warning.

        Args:
            track: The updated track (post-merge state).
            message: The ``Link16Message`` that triggered the update,
                or ``None`` for aging transitions.
        """
        if self._formatter is None:
            return

        # track is already a snapshot (deep-enough copy) from
        # TrackDatabase._notify_listeners — no need to copy again.
        try:
            self._queue.put_nowait((track, message))
        except queue.Full:
            self._drop_count += 1
            now = time.monotonic()
            if now - self._last_drop_log >= _QUEUE_FULL_LOG_INTERVAL:
                logger.warning(
                    "Network sink %s queue full — dropped %d updates so far "
                    "(remote endpoint may be unreachable or too slow)",
                    self.name, self._drop_count,
                )
                self._last_drop_log = now

    def _reconnect(self) -> bool:
        """Attempt to re-establish a TCP connection with exponential backoff.

        Returns:
            True if reconnection succeeded, False if shutdown was
            requested during the backoff loop.
        """
        delay = _RECONNECT_INITIAL
        while self._running:
            # Close the broken socket before retrying
            if self._socket is not None:
                try:
                    self._socket.close()
                except OSError:
                    pass
                self._socket = None

            logger.info(
                "Network sink %s reconnecting in %.0fs...", self.name, delay,
            )
            # Sleep in small increments so we notice shutdown quickly
            deadline = time.monotonic() + delay
            while time.monotonic() < deadline:
                if not self._running:
                    return False
                time.sleep(min(0.5, deadline - time.monotonic()))

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.connect((self._host, self._port))
                self._socket = sock
                logger.info("Network sink %s reconnected", self.name)
                return True
            except OSError as exc:
                sock.close()
                logger.warning(
                    "Network sink %s reconnect failed: %s", self.name, exc,
                )
                delay = min(delay * _RECONNECT_MULTIPLIER, _RECONNECT_MAX)

        return False

    def _sender_loop(self) -> None:
        """Background thread: drain the queue, format, and send over the socket."""
        header_sent = False

        while self._running or not self._queue.empty():
            try:
                item = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            # None is the poison pill — exit
            if item is None:
                break

            if self._socket is None or self._formatter is None:
                continue

            track, _message = item

            # Format the track — catch any formatter error so a single
            # bad track doesn't kill the entire output stream.
            try:
                formatted = self._formatter.format(track)
            except Exception as exc:
                logger.error(
                    "Network sink %s — formatter error for STN %d: %s",
                    self.name, track.stn, exc,
                )
                continue

            try:
                # If the formatter has a header() method (e.g. CSV),
                # emit it once before the first data row (and again
                # after each TCP reconnection).
                if not header_sent:
                    header_fn = getattr(self._formatter, "header", None)
                    if header_fn is not None:
                        header_data = (header_fn() + "\n").encode("utf-8")
                        self._socket.sendall(header_data)
                    header_sent = True

                data = (formatted + "\n").encode("utf-8")
                if self._protocol == "tcp":
                    self._socket.sendall(data)
                else:
                    self._socket.sendto(data, (self._host, self._port))
            except OSError as exc:
                logger.error(
                    "Network sink %s send error: %s", self.name, exc,
                )
                if self._protocol == "udp":
                    # UDP is connectionless — a single sendto failure
                    # is not fatal, just skip this message.
                    continue
                # TCP: attempt reconnection with backoff
                header_sent = False
                if not self._reconnect():
                    break

        logger.info("Network sink %s sender thread exiting", self.name)
