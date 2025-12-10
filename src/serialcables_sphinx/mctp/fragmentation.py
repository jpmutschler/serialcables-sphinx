"""
MCTP Message Fragmentation and Reassembly

Hardware constraints:
- TX limit: 128 bytes per packet (including all headers and PEC)
- RX limit: 256 bytes per packet (MCU memory constraint)
- Timing: Fragments must arrive close together for device reassembly

MCTP packet structure:
  [SMBus Header: 3 bytes] [MCTP Header: 4 bytes] [Payload: N bytes] [PEC: 1 byte]

  SMBus Header:
    - Byte 0: Destination address (7-bit << 1)
    - Byte 1: Command code (0x0F for MCTP)
    - Byte 2: Byte count (remaining bytes before PEC)

  MCTP Header byte 3 flags:
    - Bit 7: SOM (Start of Message)
    - Bit 6: EOM (End of Message)
    - Bits 5:4: Packet Sequence (0-3, wraps)
    - Bit 3: TO (Tag Owner)
    - Bits 2:0: Message Tag

Fragmentation rules:
  - Single packet: SOM=1, EOM=1, Pkt Seq=0
  - Multi-packet first: SOM=1, EOM=0, Pkt Seq=0
  - Multi-packet middle: SOM=0, EOM=0, Pkt Seq=1,2,3,0,1...
  - Multi-packet last: SOM=0, EOM=1, Pkt Seq=N
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


class FragmentationConstants:
    """Hardware-defined fragmentation limits."""

    # Maximum total packet size (TX direction)
    MAX_TX_PACKET_SIZE = 128

    # Maximum total packet size (RX direction - MCU limit)
    MAX_RX_PACKET_SIZE = 256

    # Overhead breakdown
    SMBUS_HEADER_SIZE = 3  # addr + cmd + byte_count
    MCTP_HEADER_SIZE = 4  # 4-byte MCTP transport header
    PEC_SIZE = 1  # CRC-8 at end

    # Fixed overhead per packet
    PACKET_OVERHEAD = SMBUS_HEADER_SIZE + MCTP_HEADER_SIZE + PEC_SIZE  # 8 bytes

    # Maximum payload per TX packet
    MAX_TX_PAYLOAD = MAX_TX_PACKET_SIZE - PACKET_OVERHEAD  # 120 bytes

    # Maximum payload per RX packet
    MAX_RX_PAYLOAD = MAX_RX_PACKET_SIZE - PACKET_OVERHEAD  # 248 bytes

    # Default inter-fragment delay (milliseconds)
    # Devices typically need fragments within 100-500ms
    DEFAULT_INTER_FRAGMENT_DELAY_MS = 5.0

    # Maximum inter-fragment delay before device timeout
    MAX_INTER_FRAGMENT_DELAY_MS = 100.0

    # Reassembly timeout (how long to wait for all fragments)
    REASSEMBLY_TIMEOUT_MS = 500.0


class PacketSequence:
    """Manages MCTP packet sequence numbers (2-bit, wraps 0-3)."""

    def __init__(self):
        self._seq = 0

    def current(self) -> int:
        return self._seq

    def next(self) -> int:
        """Get current and advance to next."""
        current = self._seq
        self._seq = (self._seq + 1) & 0x03  # Wrap at 4
        return current

    def reset(self):
        self._seq = 0

    def expect_next(self, received: int) -> bool:
        """Check if received sequence is expected, advance if so."""
        if received == self._seq:
            self._seq = (self._seq + 1) & 0x03
            return True
        return False


@dataclass
class MCTPFragment:
    """A single MCTP packet fragment."""

    data: bytes  # Complete packet bytes (ready to send)
    sequence: int  # Packet sequence number (0-3)
    is_first: bool  # SOM flag
    is_last: bool  # EOM flag
    payload_offset: int  # Offset of this fragment's payload in original message
    payload_length: int  # Length of payload in this fragment

    @property
    def som(self) -> bool:
        return self.is_first

    @property
    def eom(self) -> bool:
        return self.is_last


@dataclass
class FragmentedMessage:
    """A complete message split into fragments."""

    fragments: list[MCTPFragment]
    total_payload_length: int
    message_tag: int

    @property
    def fragment_count(self) -> int:
        return len(self.fragments)

    @property
    def is_fragmented(self) -> bool:
        return len(self.fragments) > 1

    def get_packets(self) -> list[bytes]:
        """Get raw packet bytes for all fragments."""
        return [f.data for f in self.fragments]


@dataclass
class ReassemblyBuffer:
    """Buffer for reassembling fragmented responses."""

    message_tag: int
    source_eid: int
    expected_seq: PacketSequence = field(default_factory=PacketSequence)
    fragments: list[bytes] = field(default_factory=list)  # Payload portions only
    started: bool = False
    complete: bool = False
    start_time: float = 0.0
    error: str | None = None

    def add_fragment(self, payload: bytes, seq: int, som: bool, eom: bool) -> bool:
        """
        Add a fragment to the buffer.

        Returns True if fragment was accepted, False on error.
        """
        now = time.time()

        # Check for timeout
        if (
            self.started
            and (now - self.start_time) * 1000 > FragmentationConstants.REASSEMBLY_TIMEOUT_MS
        ):
            self.error = "Reassembly timeout"
            return False

        # First fragment must have SOM
        if not self.started:
            if not som:
                self.error = f"Expected SOM on first fragment, got seq={seq}"
                return False
            self.started = True
            self.start_time = now
            self.expected_seq.reset()

        # Check sequence
        if not self.expected_seq.expect_next(seq):
            self.error = f"Sequence error: expected {self.expected_seq.current()}, got {seq}"
            return False

        # Store payload
        self.fragments.append(payload)

        # Check for completion
        if eom:
            self.complete = True

        return True

    def get_complete_payload(self) -> bytes | None:
        """Get reassembled payload if complete."""
        if not self.complete:
            return None
        return b"".join(self.fragments)

    def reset(self):
        """Reset buffer for new message."""
        self.expected_seq.reset()
        self.fragments.clear()
        self.started = False
        self.complete = False
        self.start_time = 0.0
        self.error = None


class MessageFragmenter:
    """
    Handles fragmenting outgoing MCTP messages.

    Takes a complete NVMe-MI message payload and splits it into
    properly-framed MCTP packets that fit within TX limits.
    """

    def __init__(
        self,
        max_payload_per_packet: int = FragmentationConstants.MAX_TX_PAYLOAD,
    ):
        self.max_payload = max_payload_per_packet
        self._pkt_seq = PacketSequence()

    def calculate_fragment_count(self, payload_length: int) -> int:
        """Calculate how many fragments are needed for a payload."""
        if payload_length <= self.max_payload:
            return 1
        return (payload_length + self.max_payload - 1) // self.max_payload

    def fragment_payload(self, payload: bytes) -> list[tuple[bytes, int, bool, bool]]:
        """
        Split payload into fragments.

        Returns list of (fragment_data, pkt_seq, som, eom) tuples.
        These are just the payload portions - caller adds MCTP/SMBus framing.
        """
        if len(payload) <= self.max_payload:
            # Single packet
            return [(payload, 0, True, True)]

        fragments = []
        offset = 0
        self._pkt_seq.reset()

        while offset < len(payload):
            chunk = payload[offset : offset + self.max_payload]
            is_first = offset == 0
            is_last = offset + len(chunk) >= len(payload)
            seq = self._pkt_seq.next()

            fragments.append((chunk, seq, is_first, is_last))
            offset += len(chunk)

        return fragments


class MessageReassembler:
    """
    Handles reassembling incoming fragmented MCTP responses.

    Buffers fragments until complete message is received,
    with timeout handling for incomplete transmissions.
    """

    def __init__(self):
        self._buffers: dict[tuple[int, int], ReassemblyBuffer] = {}  # (tag, src_eid) -> buffer

    def process_fragment(
        self,
        payload: bytes,
        msg_tag: int,
        src_eid: int,
        pkt_seq: int,
        som: bool,
        eom: bool,
    ) -> bytes | None:
        """
        Process an incoming fragment.

        Returns complete reassembled payload when EOM received,
        None if still waiting for more fragments.

        Raises ValueError on reassembly errors.
        """
        key = (msg_tag, src_eid)

        # Get or create buffer
        if som:
            # New message - create fresh buffer
            self._buffers[key] = ReassemblyBuffer(
                message_tag=msg_tag,
                source_eid=src_eid,
            )

        buffer = self._buffers.get(key)
        if buffer is None:
            raise ValueError(f"Received fragment without SOM for tag={msg_tag}, eid={src_eid}")

        # Add fragment
        if not buffer.add_fragment(payload, pkt_seq, som, eom):
            error = buffer.error
            del self._buffers[key]
            raise ValueError(f"Reassembly error: {error}")

        # Check for completion
        if buffer.complete:
            complete_payload = buffer.get_complete_payload()
            del self._buffers[key]
            return complete_payload

        return None

    def cleanup_stale(self, max_age_ms: float = FragmentationConstants.REASSEMBLY_TIMEOUT_MS):
        """Remove stale incomplete buffers."""
        now = time.time()
        stale_keys = []

        for key, buffer in self._buffers.items():
            if buffer.started and (now - buffer.start_time) * 1000 > max_age_ms:
                stale_keys.append(key)

        for key in stale_keys:
            del self._buffers[key]

    def pending_count(self) -> int:
        """Number of messages awaiting more fragments."""
        return len(self._buffers)

    def reset(self):
        """Clear all reassembly state."""
        self._buffers.clear()


@dataclass
class FragmentationConfig:
    """Configuration for fragmentation behavior."""

    # Maximum payload bytes per TX packet
    max_tx_payload: int = FragmentationConstants.MAX_TX_PAYLOAD

    # Maximum payload bytes per RX packet
    max_rx_payload: int = FragmentationConstants.MAX_RX_PAYLOAD

    # Delay between sending fragments (ms)
    inter_fragment_delay_ms: float = FragmentationConstants.DEFAULT_INTER_FRAGMENT_DELAY_MS

    # Timeout waiting for response fragments (ms)
    reassembly_timeout_ms: float = FragmentationConstants.REASSEMBLY_TIMEOUT_MS

    # Whether to validate packet sequences strictly
    strict_sequence_check: bool = True

    def validate(self):
        """Validate configuration values."""
        if self.max_tx_payload > FragmentationConstants.MAX_TX_PAYLOAD:
            raise ValueError(
                f"max_tx_payload ({self.max_tx_payload}) exceeds hardware limit "
                f"({FragmentationConstants.MAX_TX_PAYLOAD})"
            )
        if self.max_rx_payload > FragmentationConstants.MAX_RX_PAYLOAD:
            raise ValueError(
                f"max_rx_payload ({self.max_rx_payload}) exceeds hardware limit "
                f"({FragmentationConstants.MAX_RX_PAYLOAD})"
            )
        if self.inter_fragment_delay_ms < 0:
            raise ValueError("inter_fragment_delay_ms cannot be negative")
        if self.inter_fragment_delay_ms > FragmentationConstants.MAX_INTER_FRAGMENT_DELAY_MS:
            raise ValueError(
                f"inter_fragment_delay_ms ({self.inter_fragment_delay_ms}) exceeds "
                f"maximum safe delay ({FragmentationConstants.MAX_INTER_FRAGMENT_DELAY_MS})"
            )
