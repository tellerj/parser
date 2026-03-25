"""Tests for the network output sink."""

from __future__ import annotations

import socket
import struct
import threading
import time
from datetime import datetime, timezone
import pytest

from link16_parser.core.types import Track
from link16_parser.network.sink import NetworkSink

TS = datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc)


def _track(stn: int = 100, callsign: str | None = "VIPER01") -> Track:
    return Track(stn=stn, callsign=callsign, last_updated=TS)


class _EchoFormatter:
    """Minimal formatter that returns the callsign (or STN) as a string."""

    @property
    def name(self) -> str:
        return "ECHO"

    def format(self, track: Track) -> str:
        return track.callsign or f"STN{track.stn}"


class _HeaderFormatter(_EchoFormatter):
    """Formatter with a header() method, like CsvFormatter."""

    def header(self) -> str:
        return "HDR"


class _BrokenFormatter:
    """Formatter that always raises."""

    @property
    def name(self) -> str:
        return "BROKEN"

    def format(self, track: Track) -> str:  # noqa: ARG002
        raise ValueError("bad track")


def _listen_tcp(ready: threading.Event) -> tuple[socket.socket, int]:
    """Start a TCP server socket on localhost, signal when ready."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    ready.set()
    return srv, srv.getsockname()[1]


# ---------------------------------------------------------------------------
# Basic TCP send
# ---------------------------------------------------------------------------


class TestTcpSend:
    def test_sends_formatted_track(self) -> None:
        ready = threading.Event()
        srv, port = _listen_tcp(ready)
        ready.wait()

        try:
            sink = NetworkSink("127.0.0.1", port, "tcp", _EchoFormatter())
            sink.start()

            conn, _ = srv.accept()
            try:
                sink.on_track_update(_track(), None)
                # Give the sender thread time to drain
                time.sleep(0.3)
                sink.stop()

                data = conn.recv(4096).decode()
                assert data == "VIPER01\n"
            finally:
                conn.close()
        finally:
            srv.close()

    def test_sends_header_once(self) -> None:
        ready = threading.Event()
        srv, port = _listen_tcp(ready)
        ready.wait()

        try:
            sink = NetworkSink("127.0.0.1", port, "tcp", _HeaderFormatter())
            sink.start()

            conn, _ = srv.accept()
            try:
                sink.on_track_update(_track(stn=1), None)
                sink.on_track_update(_track(stn=2, callsign="EAGLE01"), None)
                time.sleep(0.3)
                sink.stop()

                data = conn.recv(4096).decode()
                lines = data.strip().split("\n")
                assert lines[0] == "HDR"
                assert lines[1] == "VIPER01"
                assert lines[2] == "EAGLE01"
                # Header only appears once
                assert data.count("HDR") == 1
            finally:
                conn.close()
        finally:
            srv.close()


# ---------------------------------------------------------------------------
# UDP send
# ---------------------------------------------------------------------------


class TestUdpSend:
    def test_sends_over_udp(self) -> None:
        recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        recv_sock.bind(("127.0.0.1", 0))
        port = recv_sock.getsockname()[1]
        recv_sock.settimeout(2.0)

        try:
            sink = NetworkSink("127.0.0.1", port, "udp", _EchoFormatter())
            sink.start()

            sink.on_track_update(_track(), None)
            time.sleep(0.3)
            sink.stop()

            data, _ = recv_sock.recvfrom(4096)
            assert data.decode() == "VIPER01\n"
        finally:
            recv_sock.close()


# ---------------------------------------------------------------------------
# Queue full / drop behavior
# ---------------------------------------------------------------------------


class TestQueueDrop:
    def test_drops_when_queue_full(self) -> None:
        sink = NetworkSink("127.0.0.1", 1, "tcp", _EchoFormatter(), queue_size=2)
        # Don't start — no sender thread draining, so queue fills up
        sink._running = True  # pyright: ignore[reportPrivateUsage]

        sink.on_track_update(_track(stn=1), None)
        sink.on_track_update(_track(stn=2), None)
        # Third should be dropped
        sink.on_track_update(_track(stn=3), None)

        assert sink._drop_count == 1  # pyright: ignore[reportPrivateUsage]
        assert sink._queue.qsize() == 2  # pyright: ignore[reportPrivateUsage]


# ---------------------------------------------------------------------------
# No formatter → no-op
# ---------------------------------------------------------------------------


class TestNoFormatter:
    def test_no_formatter_skips_enqueue(self) -> None:
        sink = NetworkSink("127.0.0.1", 1, "tcp", formatter=None)
        sink.on_track_update(_track(), None)
        assert sink._queue.qsize() == 0  # pyright: ignore[reportPrivateUsage]


# ---------------------------------------------------------------------------
# Formatter error handling (#4)
# ---------------------------------------------------------------------------


class TestFormatterError:
    def test_formatter_error_does_not_kill_sender(self) -> None:
        ready = threading.Event()
        srv, port = _listen_tcp(ready)
        ready.wait()

        try:
            sink = NetworkSink("127.0.0.1", port, "tcp", _BrokenFormatter())
            sink.start()

            conn, _ = srv.accept()
            try:
                # Send a track that will cause a formatter error
                sink.on_track_update(_track(stn=1), None)
                time.sleep(0.3)

                # Swap in a working formatter — sender thread should still be alive
                sink._formatter = _EchoFormatter()  # pyright: ignore[reportPrivateUsage]
                sink.on_track_update(_track(stn=2, callsign="ALIVE"), None)
                time.sleep(0.3)
                sink.stop()

                data = conn.recv(4096).decode()
                assert "ALIVE" in data
            finally:
                conn.close()
        finally:
            srv.close()


# ---------------------------------------------------------------------------
# TCP reconnection (#1)
# ---------------------------------------------------------------------------


class TestTcpReconnect:
    def test_reconnects_after_server_drops(self) -> None:
        """Sender reconnects when the remote end closes the connection."""
        ready = threading.Event()
        srv, port = _listen_tcp(ready)
        ready.wait()

        try:
            sink = NetworkSink("127.0.0.1", port, "tcp", _EchoFormatter())
            sink.start()

            # Accept first connection, receive one message, then RST it
            conn1, _ = srv.accept()
            sink.on_track_update(_track(stn=1, callsign="MSG1"), None)
            time.sleep(0.3)
            data1 = conn1.recv(4096).decode()
            assert "MSG1" in data1
            # RST instead of graceful close so sendall fails fast
            conn1.setsockopt(
                socket.SOL_SOCKET, socket.SO_LINGER,
                struct.pack("ii", 1, 0),
            )
            conn1.close()

            # Flood sends to ensure the sender thread hits the broken pipe
            for i in range(20):
                sink.on_track_update(_track(stn=i + 10, callsign=f"FLOOD{i}"), None)
            time.sleep(0.5)

            # Accept the reconnection
            srv.settimeout(5.0)
            conn2, _ = srv.accept()
            try:
                time.sleep(1.5)
                sink.on_track_update(_track(stn=99, callsign="MSG3"), None)
                time.sleep(0.3)
                sink.stop()

                data2 = conn2.recv(4096).decode()
                assert "MSG3" in data2
            finally:
                conn2.close()
        finally:
            srv.close()

    def test_header_resent_after_reconnect(self) -> None:
        """CSV header is re-sent on each new TCP connection."""
        ready = threading.Event()
        srv, port = _listen_tcp(ready)
        ready.wait()

        try:
            sink = NetworkSink("127.0.0.1", port, "tcp", _HeaderFormatter())
            sink.start()

            # First connection — header + data
            conn1, _ = srv.accept()
            sink.on_track_update(_track(stn=1), None)
            time.sleep(0.3)
            data1 = conn1.recv(4096).decode()
            assert data1.startswith("HDR\n")
            # RST so sendall fails fast
            conn1.setsockopt(
                socket.SOL_SOCKET, socket.SO_LINGER,
                struct.pack("ii", 1, 0),
            )
            conn1.close()

            # Flood sends to trigger broken pipe
            for i in range(20):
                sink.on_track_update(_track(stn=i + 10, callsign=f"FLOOD{i}"), None)
            time.sleep(0.5)

            srv.settimeout(5.0)
            conn2, _ = srv.accept()
            try:
                time.sleep(1.5)
                sink.on_track_update(_track(stn=99, callsign="AFTER"), None)
                time.sleep(0.3)
                sink.stop()

                data2 = conn2.recv(4096).decode()
                # Header should appear again on the new connection
                assert "HDR\n" in data2
            finally:
                conn2.close()
        finally:
            srv.close()


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------


class TestShutdown:
    def test_stop_is_idempotent(self) -> None:
        ready = threading.Event()
        srv, port = _listen_tcp(ready)
        ready.wait()

        try:
            sink = NetworkSink("127.0.0.1", port, "tcp", _EchoFormatter())
            sink.start()
            conn, _ = srv.accept()
            try:
                sink.stop()
                sink.stop()  # Should not raise
            finally:
                conn.close()
        finally:
            srv.close()

    def test_stop_logs_drop_count(self, caplog: pytest.LogCaptureFixture) -> None:
        sink = NetworkSink("127.0.0.1", 1, "tcp", _EchoFormatter(), queue_size=1)
        sink._running = True  # pyright: ignore[reportPrivateUsage]
        sink.on_track_update(_track(stn=1), None)
        sink.on_track_update(_track(stn=2), None)  # dropped

        sink._running = False  # pyright: ignore[reportPrivateUsage]
        sink.stop()

        assert any("dropped 1" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Protocol validation
# ---------------------------------------------------------------------------


class TestProtocol:
    def test_invalid_protocol_raises(self) -> None:
        sink = NetworkSink("127.0.0.1", 1, "ftp", _EchoFormatter())
        with pytest.raises(ValueError, match="ftp"):
            sink.start()

    def test_tcp_connection_refused(self) -> None:
        # Use a port that is almost certainly not listening
        sink = NetworkSink("127.0.0.1", 1, "tcp", _EchoFormatter())
        with pytest.raises((ConnectionRefusedError, OSError)):
            sink.start()
