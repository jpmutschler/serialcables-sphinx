"""
MCTP packet builder for constructing properly framed MCTP messages.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from serialcables_sphinx.mctp.header import MCTPHeader
from serialcables_sphinx.mctp.constants import (
    MCTPMessageType,
    MCTP_SMBUS_COMMAND_CODE,
    DEFAULT_SOURCE_EID,
    DEFAULT_SMBUS_ADDRESS,
)


@dataclass
class MCTPBuilder:
    """
    Builder for MCTP packets over SMBus/I2C.
    
    Constructs complete MCTP frames including SMBus framing,
    MCTP transport header, and message payload.
    
    Attributes:
        smbus_addr: Target SMBus address (default 0x3A for NVMe-MI)
        src_eid: Source Endpoint ID (default 0x00 for host/BMC)
        auto_pec: Automatically calculate and append PEC byte
        
    Example:
        builder = MCTPBuilder()
        
        # Build NVMe-MI request
        packet = builder.build_nvme_mi_request(
            dest_eid=1,
            payload=bytes([0x01, 0x00, 0x00, 0x00])  # Health poll
        )
        
        # Build raw MCTP packet
        packet = builder.build_raw(
            dest_eid=1,
            msg_type=MCTPMessageType.NVME_MI,
            payload=my_payload
        )
    """
    smbus_addr: int = DEFAULT_SMBUS_ADDRESS
    src_eid: int = DEFAULT_SOURCE_EID
    auto_pec: bool = True
    _msg_tag: int = field(default=0, repr=False)
    
    def build_raw(
        self,
        dest_eid: int,
        msg_type: int,
        payload: bytes,
        src_eid: Optional[int] = None,
        som: bool = True,
        eom: bool = True,
        pkt_seq: int = 0,
        msg_tag: Optional[int] = None,
        tag_owner: bool = True,
        smbus_addr: Optional[int] = None,
        include_pec: Optional[bool] = None,
    ) -> bytes:
        """
        Build a complete MCTP-over-SMBus packet.
        
        Args:
            dest_eid: Destination Endpoint ID
            msg_type: MCTP message type (e.g., MCTPMessageType.NVME_MI)
            payload: Message payload bytes (after message type byte)
            src_eid: Source EID (uses instance default if None)
            som: Start of Message flag
            eom: End of Message flag
            pkt_seq: Packet sequence number (0-3)
            msg_tag: Message tag (auto-increments if None)
            tag_owner: Tag owner flag
            smbus_addr: Target SMBus address (uses instance default if None)
            include_pec: Include PEC byte (uses instance auto_pec if None)
            
        Returns:
            Complete packet bytes ready for transmission
        """
        # Use defaults
        src_eid = src_eid if src_eid is not None else self.src_eid
        smbus_addr = smbus_addr if smbus_addr is not None else self.smbus_addr
        include_pec = include_pec if include_pec is not None else self.auto_pec
        
        # Auto-increment message tag if not specified
        if msg_tag is None:
            msg_tag = self._msg_tag
            self._msg_tag = (self._msg_tag + 1) & 0x07
        
        # Build MCTP header
        header = MCTPHeader(
            dest_eid=dest_eid,
            src_eid=src_eid,
            som=som,
            eom=eom,
            pkt_seq=pkt_seq,
            tag_owner=tag_owner,
            msg_tag=msg_tag,
        )
        
        # MCTP message = header + message type + payload
        mctp_message = header.pack() + bytes([msg_type]) + payload
        
        # SMBus framing
        byte_count = len(mctp_message)
        packet = bytes([
            smbus_addr,
            MCTP_SMBUS_COMMAND_CODE,
            byte_count,
        ]) + mctp_message
        
        # Add PEC if requested
        if include_pec:
            packet += bytes([self.calculate_pec(packet)])
        
        return packet
    
    def build_nvme_mi_request(
        self,
        dest_eid: int,
        payload: bytes,
        integrity_check: bool = False,
        **kwargs,
    ) -> bytes:
        """
        Build an NVMe-MI request packet.
        
        The payload should be the NVMe-MI request data starting from
        the opcode byte (not including the message type byte).
        
        Args:
            dest_eid: Destination Endpoint ID
            payload: NVMe-MI request payload (opcode + parameters)
            integrity_check: Set integrity check flag in message type
            **kwargs: Additional arguments passed to build_raw()
            
        Returns:
            Complete MCTP packet with NVMe-MI request
            
        Example:
            # Build health status poll request
            packet = builder.build_nvme_mi_request(
                dest_eid=1,
                payload=bytes([0x01, 0x00, 0x00, 0x00])  # Opcode 0x01
            )
        """
        msg_type = MCTPMessageType.NVME_MI
        if integrity_check:
            msg_type |= 0x80  # Set IC bit
        
        return self.build_raw(
            dest_eid=dest_eid,
            msg_type=msg_type,
            payload=payload,
            **kwargs,
        )
    
    def build_mctp_control(
        self,
        dest_eid: int,
        command: int,
        payload: bytes = b"",
        **kwargs,
    ) -> bytes:
        """
        Build an MCTP Control message.
        
        Args:
            dest_eid: Destination Endpoint ID
            command: MCTP Control command code
            payload: Command-specific payload
            **kwargs: Additional arguments passed to build_raw()
            
        Returns:
            Complete MCTP packet with control message
        """
        # Control message: [IC/Rq/D/rsvd/InstID] [Command] [Payload...]
        control_header = bytes([
            0x80,  # Rq=1 (request), D=0, InstID=0
            command,
        ])
        
        return self.build_raw(
            dest_eid=dest_eid,
            msg_type=MCTPMessageType.MCTP_CONTROL,
            payload=control_header + payload,
            **kwargs,
        )
    
    @staticmethod
    def calculate_pec(data: bytes) -> int:
        """
        Calculate SMBus Packet Error Code (CRC-8).
        
        Uses polynomial x^8 + x^2 + x^1 + 1 (0x07).
        
        Args:
            data: Bytes to calculate PEC over
            
        Returns:
            8-bit PEC value
        """
        crc = 0
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x80:
                    crc = (crc << 1) ^ 0x07
                else:
                    crc <<= 1
                crc &= 0xFF
        return crc
    
    def to_cli_format(self, dest_eid: int, packet: bytes) -> str:
        """
        Convert packet to HYDRA CLI command format.
        
        Args:
            dest_eid: Destination EID (for command prefix)
            packet: Complete packet bytes
            
        Returns:
            CLI command string like "packet 7 3a f 11..."
        """
        hex_bytes = " ".join(f"{b:x}" for b in packet)
        return f"packet {dest_eid} {hex_bytes}"
    
    def reset_tag(self) -> None:
        """Reset message tag counter to 0."""
        self._msg_tag = 0
    
    @property
    def current_tag(self) -> int:
        """Get current message tag value (next to be used)."""
        return self._msg_tag
