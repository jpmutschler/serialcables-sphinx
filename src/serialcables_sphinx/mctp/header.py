"""
MCTP Transport Header implementation per DSP0236.
"""

from __future__ import annotations

from dataclasses import dataclass

from serialcables_sphinx.mctp.constants import MCTP_HEADER_VERSION


@dataclass
class MCTPHeader:
    """
    MCTP Transport Header (4 bytes).

    Per DSP0236 Section 8.1, the transport header contains:
    - Header version (4 bits)
    - Destination endpoint ID (8 bits)
    - Source endpoint ID (8 bits)
    - Message flags and tag (8 bits)

    Attributes:
        header_version: MCTP header version (should be 0x01)
        dest_eid: Destination Endpoint ID (0x00 = NULL, 0xFF = broadcast)
        src_eid: Source Endpoint ID
        som: Start of Message flag
        eom: End of Message flag
        pkt_seq: Packet sequence number (0-3) for fragmented messages
        tag_owner: Message tag owner (True = originator)
        msg_tag: Message tag for request/response correlation (0-7)
    """

    dest_eid: int = 0x01
    src_eid: int = 0x00
    som: bool = True
    eom: bool = True
    pkt_seq: int = 0
    tag_owner: bool = True
    msg_tag: int = 0
    header_version: int = MCTP_HEADER_VERSION

    def pack(self) -> bytes:
        """
        Pack header into 4 bytes for transmission.

        Byte layout:
            Byte 0: [Reserved:4][Header Version:4]
            Byte 1: Destination EID
            Byte 2: Source EID
            Byte 3: [SOM:1][EOM:1][PktSeq:2][TO:1][MsgTag:3]

        Returns:
            4-byte header ready for transmission
        """
        byte0 = self.header_version & 0x0F  # Upper nibble reserved

        byte3 = (
            (int(self.som) << 7)
            | (int(self.eom) << 6)
            | ((self.pkt_seq & 0x03) << 4)
            | (int(self.tag_owner) << 3)
            | (self.msg_tag & 0x07)
        )

        return bytes([byte0, self.dest_eid, self.src_eid, byte3])

    @classmethod
    def unpack(cls, data: bytes) -> MCTPHeader:
        """
        Unpack 4 bytes into MCTPHeader.

        Args:
            data: At least 4 bytes of header data

        Returns:
            Parsed MCTPHeader instance

        Raises:
            ValueError: If data is less than 4 bytes
        """
        if len(data) < 4:
            raise ValueError(f"MCTP header requires 4 bytes, got {len(data)}")

        return cls(
            header_version=data[0] & 0x0F,
            dest_eid=data[1],
            src_eid=data[2],
            som=bool(data[3] & 0x80),
            eom=bool(data[3] & 0x40),
            pkt_seq=(data[3] >> 4) & 0x03,
            tag_owner=bool(data[3] & 0x08),
            msg_tag=data[3] & 0x07,
        )

    @property
    def is_single_packet(self) -> bool:
        """Check if this is a single-packet (non-fragmented) message."""
        return self.som and self.eom

    @property
    def is_first_fragment(self) -> bool:
        """Check if this is the first packet of a fragmented message."""
        return self.som and not self.eom

    @property
    def is_last_fragment(self) -> bool:
        """Check if this is the last packet of a fragmented message."""
        return not self.som and self.eom

    @property
    def is_middle_fragment(self) -> bool:
        """Check if this is a middle packet of a fragmented message."""
        return not self.som and not self.eom

    def __str__(self) -> str:
        flags = []
        if self.som:
            flags.append("SOM")
        if self.eom:
            flags.append("EOM")
        if self.tag_owner:
            flags.append("TO")

        return (
            f"MCTPHeader(dst=0x{self.dest_eid:02X}, src=0x{self.src_eid:02X}, "
            f"seq={self.pkt_seq}, tag={self.msg_tag}, flags=[{','.join(flags)}])"
        )
