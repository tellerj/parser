"""End-to-end test: synthetic PCAP through the full pipeline to TrackDatabase."""

from __future__ import annotations

import os
import tempfile

from link16_parser.encapsulation import AutoDecoder
from link16_parser.ingestion import FileSource
from link16_parser.link16 import build_parser
from link16_parser.tracks import TrackDatabase

from tests.builders import make_jword, make_simple_pcap


def test_simple_pcap_two_messages_same_stn() -> None:
    """Two different message types for the same STN merge into one track."""

    j22_word = make_jword(label=2, sublabel=2)   # J2.2 Air PPLI
    j32_word = make_jword(label=3, sublabel=2)   # J3.2 Air Track

    pcap_bytes = make_simple_pcap(
        jwords_per_packet=[[j22_word], [j32_word]],
        stn=169,
        npg=7,
    )

    # Write to a temp file so FileSource can open it by path
    fd, path = tempfile.mkstemp(suffix=".pcap")
    try:
        os.write(fd, pcap_bytes)
        os.close(fd)

        source = FileSource(path)
        encap_decoder = AutoDecoder()
        jword_parser = build_parser()
        track_db = TrackDatabase()

        # Run the pipeline inline (no threading needed for tests)
        for pcap_ts, payload in source.packets():
            raw_words = encap_decoder.decode(payload, pcap_ts)
            if not raw_words:
                continue
            messages = jword_parser.parse(raw_words)
            for msg in messages:
                track_db.update(msg)

        # Assertions
        assert len(track_db) == 1

        track = track_db.get_by_stn(169)
        assert track is not None
        assert track.stn == 169
        assert track.message_count == 2
        assert track.last_updated is not None

    finally:
        os.unlink(path)


def test_multiple_stns_create_separate_tracks() -> None:
    """Different STNs produce distinct tracks."""

    j22_word = make_jword(label=2, sublabel=2)

    # Two packets with different STNs — need to build manually since
    # make_simple_pcap uses a single STN for all packets
    from tests.builders import make_pcap_file, make_simple_payload, make_udp_frame

    pkt1 = make_udp_frame(make_simple_payload([j22_word], stn=100))
    pkt2 = make_udp_frame(make_simple_payload([j22_word], stn=200))
    pcap_bytes = make_pcap_file([(1_700_000_000.0, pkt1), (1_700_000_001.0, pkt2)])

    fd, path = tempfile.mkstemp(suffix=".pcap")
    try:
        os.write(fd, pcap_bytes)
        os.close(fd)

        source = FileSource(path)
        encap_decoder = AutoDecoder()
        jword_parser = build_parser()
        track_db = TrackDatabase()

        for pcap_ts, payload in source.packets():
            raw_words = encap_decoder.decode(payload, pcap_ts)
            if not raw_words:
                continue
            messages = jword_parser.parse(raw_words)
            for msg in messages:
                track_db.update(msg)

        assert len(track_db) == 2
        assert track_db.get_by_stn(100) is not None
        assert track_db.get_by_stn(200) is not None

    finally:
        os.unlink(path)
