"""JREAP-C (MIL-STD-3011) encapsulation decoder — STUB.

JREAP-C is the operational protocol used by JRE systems to transport
Link 16 messages over IP. The detailed header format is defined in
MIL-STD-3011 (Distribution C restricted) and is NOT publicly available.

This stub exists so the architecture is ready to accept a real implementation
once the spec is obtained or the wire format is reverse-engineered from
captured traffic.

TODO: Implement once MIL-STD-3011 details or capture analysis is available.
"""

from __future__ import annotations

import logging

from jreap_parser.core.types import RawJWord

logger = logging.getLogger(__name__)


class JreapCDecoder:
    """Stub decoder for JREAP-C encapsulated Link 16 packets.

    Currently returns empty results. Replace internals once the
    JREAP-C header format (TBH, MGH, Application Header) is known.
    """

    @property
    def name(self) -> str:
        return "JREAP-C"

    def decode(self, payload: bytes, pcap_timestamp: float) -> list[RawJWord]:
        # TODO: Implement JREAP-C decapsulation
        # Expected structure (from open literature):
        #   - Transmission Block Header (TBH)
        #   - Message Group Header (MGH)
        #   - Application Header
        #   - Link 16 message payload (J-words)
        #
        # Pending: MIL-STD-3011 access or capture-based reverse engineering.
        return []
