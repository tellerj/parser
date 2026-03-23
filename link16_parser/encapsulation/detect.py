"""Auto-detection of encapsulation format from packet payload.

Inspects the first bytes of a payload to determine which decoder to use.
Falls back to trying all decoders if heuristics are inconclusive.
"""

from __future__ import annotations

import logging
from typing import Sequence

from link16_parser.core.interfaces import EncapsulationDecoder
from link16_parser.core.types import RawJWord
from link16_parser.encapsulation.simple import SYNC_BYTE_1, SYNC_BYTE_2
from link16_parser.encapsulation.siso_j import DIS_SIGNAL_PDU_TYPE

logger = logging.getLogger(__name__)


class AutoDecoder:
    """Heuristic dispatcher that detects the encapsulation format per-packet.

    Detection strategy (checked in order):
        1. Bytes 0-1 are ``0x49 0x36`` -> SIMPLE.
        2. Byte 2 is ``0x1A`` (26) -> DIS Signal PDU (SISO-J).
        3. Fallback: try each decoder and return the first non-empty result.

    Args:
        decoders: Sequence of ``EncapsulationDecoder`` instances to use.
            If ``None``, defaults to ``[SimpleDecoder(), SisoJDecoder(),
            JreapCDecoder()]``.
    """

    def __init__(self, decoders: Sequence[EncapsulationDecoder] | None = None) -> None:
        if decoders is None:
            from link16_parser.encapsulation.simple import SimpleDecoder
            from link16_parser.encapsulation.siso_j import SisoJDecoder
            from link16_parser.encapsulation.jreap_c import JreapCDecoder
            decoders = [SimpleDecoder(), SisoJDecoder(), JreapCDecoder()]
        self._decoders = list(decoders)
        self._by_name = {d.name: d for d in self._decoders}

    @property
    def name(self) -> str:
        return "Auto"

    def decode(self, payload: bytes, pcap_timestamp: float) -> list[RawJWord]:
        """Detect the encapsulation format and decode.

        Args:
            payload: Raw UDP/TCP payload bytes.
            pcap_timestamp: Epoch-seconds timestamp from the PCAP frame.

        Returns:
            List of ``RawJWord`` objects from whichever decoder matched,
            or empty list if no decoder recognized the payload.
        """
        if len(payload) < 2:
            return []

        # SIMPLE: sync bytes 0x49 0x36
        if payload[0] == SYNC_BYTE_1 and payload[1] == SYNC_BYTE_2:
            simple = self._by_name.get("SIMPLE")
            if simple:
                return simple.decode(payload, pcap_timestamp)

        # DIS Signal PDU: PDU type at offset 2
        if len(payload) > 2 and payload[2] == DIS_SIGNAL_PDU_TYPE:
            siso_j = self._by_name.get("SISO-J")
            if siso_j:
                return siso_j.decode(payload, pcap_timestamp)

        # Fallback: try each decoder
        for decoder in self._decoders:
            words = decoder.decode(payload, pcap_timestamp)
            if words:
                return words

        logger.debug(
            "No decoder matched payload (%d bytes, first bytes: %s)",
            len(payload), payload[:8].hex(),
        )
        return []
