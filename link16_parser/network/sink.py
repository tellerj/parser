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

from link16_parser.core.interfaces import OutputFormatter
from link16_parser.core.types import Link16Message, Track

logger = logging.getLogger(__name__)


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
            Typically a ``TacrepFormatter`` or ``NineLineFormatter``.
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
        self._queue: queue.Queue[str | None] = queue.Queue(maxsize=queue_size)
        self._socket: socket.socket | None = None
        self._sender_thread: threading.Thread | None = None
        self._running = False

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
            self._socket.connect((self._host, self._port))
            logger.info("Connected to %s", self.name)
        elif self._protocol == "udp":
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            logger.info("UDP sink ready: %s", self.name)
        else:
            raise ValueError(f"Unsupported protocol: {self._protocol}")

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

    def on_track_update(self, track: Track, message: Link16Message) -> None:
        """Enqueue a formatted track update for network delivery.

        Called inside the ``TrackDatabase`` lock. Enqueues without
        blocking — if the queue is full, the update is dropped with
        a warning.

        Args:
            track: The updated track (post-merge state).
            message: The ``Link16Message`` that triggered the update.
        """
        if self._formatter is None:
            return

        formatted = self._formatter.format(track)
        try:
            self._queue.put_nowait(formatted)
        except queue.Full:
            logger.warning("Network sink queue full, dropping update for STN %d", track.stn)

    def _sender_loop(self) -> None:
        """Background thread: drain the queue and send over the socket."""
        while self._running or not self._queue.empty():
            try:
                msg = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            # None is the poison pill — exit
            if msg is None:
                break

            if self._socket is None:
                continue

            try:
                data = (msg + "\n").encode("utf-8")
                if self._protocol == "tcp":
                    self._socket.sendall(data)
                else:
                    self._socket.sendto(data, (self._host, self._port))
            except OSError:
                logger.exception("Network send error to %s", self.name)
                break
