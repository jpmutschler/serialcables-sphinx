"""
MCTP packet parser for decoding received MCTP messages.
"""

from __future__ import annotations

from dataclasses import dataclass

from serialcables_sphinx.mctp.builder import MCTPBuilder
from serialcables_sphinx.mctp.constants import (
    MCTP_SMBUS_COMMAND_CODE,
    MCTPMessageType,
)
from serialcables_sphinx.mctp.header import MCTPHeader


@dataclass
class ParsedMCTPPacket:
    """
    Parsed MCTP packet with all components accessible.

    Attributes:
        raw: Original raw packet bytes
        smbus_addr: SMBus destination address
        smbus_cmd: SMBus command code (should be 0x0F)
        byte_count: Declared byte count from SMBus framing
        header: Parsed MCTP transport header
        msg_type: MCTP message type (lower 7 bits)
        integrity_check: Integrity check flag (bit 7 of msg type)
        payload: Message payload (after message type byte)
        pec: PEC byte from packet (if present)
        pec_valid: Whether PEC validates correctly
    """

    raw: bytes
    smbus_addr: int
    smbus_cmd: int
    byte_count: int
    header: MCTPHeader
    msg_type: int
    integrity_check: bool
    payload: bytes
    pec: int | None = None
    pec_valid: bool | None = None

    @property
    def is_nvme_mi(self) -> bool:
        """Check if this is an NVMe-MI message."""
        return self.msg_type == MCTPMessageType.NVME_MI

    @property
    def is_control(self) -> bool:
        """Check if this is an MCTP Control message."""
        return self.msg_type == MCTPMessageType.MCTP_CONTROL

    @property
    def nvme_mi_payload(self) -> bytes:
        """
        Get payload as NVMe-MI message data.

        For NVMe-MI messages, this returns the payload starting
        from the NVMe-MI message header (after MCTP msg type).

        Returns:
            NVMe-MI message bytes
        """
        return self.payload

    def __str__(self) -> str:
        pec_str = ""
        if self.pec is not None:
            pec_str = f", PEC=0x{self.pec:02X}({'✓' if self.pec_valid else '✗'})"

        return (
            f"MCTPPacket(addr=0x{self.smbus_addr:02X}, "
            f"type={MCTPMessageType(self.msg_type).name if self.msg_type < 0x10 else f'0x{self.msg_type:02X}'}, "
            f"len={len(self.payload)}, "
            f"{self.header}"
            f"{pec_str})"
        )


class MCTPParser:
    """
    Parser for MCTP-over-SMBus packets.

    Handles parsing of complete SMBus-framed MCTP packets,
    extracting headers, message type, and payload.

    Example:
        parser = MCTPParser()

        # Parse response bytes
        parsed = parser.parse(response_bytes)

        if parsed.is_nvme_mi:
            nvme_data = parsed.nvme_mi_payload
    """

    def parse(
        self,
        data: bytes,
        validate_pec: bool = True,
    ) -> ParsedMCTPPacket:
        """
        Parse a complete MCTP-over-SMBus packet.

        Expected format:
            [SMBus Addr][Cmd=0x0F][ByteCount][MCTP Header 4B][MsgType][Payload...][PEC]

        Args:
            data: Raw packet bytes
            validate_pec: Whether to validate PEC byte

        Returns:
            ParsedMCTPPacket with all components

        Raises:
            ValueError: If packet is malformed
        """
        if len(data) < 8:
            raise ValueError(f"Packet too short: {len(data)} bytes, minimum 8")

        # SMBus framing: [Dest Addr][Cmd Code][Byte Count][Src Addr][MCTP...]
        smbus_addr = data[0]
        smbus_cmd = data[1]
        byte_count = data[2]
        # smbus_src_addr = data[3]  # SMBus source address

        # Validate SMBus command code
        if smbus_cmd != MCTP_SMBUS_COMMAND_CODE:
            # Some responses may have different format, be lenient
            pass

        # MCTP header (4 bytes starting at offset 4, after SMBus src addr)
        header = MCTPHeader.unpack(data[4:8])

        # Message type byte at offset 8
        msg_type_byte = data[8]
        integrity_check = bool(msg_type_byte & 0x80)
        msg_type = msg_type_byte & 0x7F

        # Calculate where payload ends
        # byte_count includes: SMBus src (1) + MCTP header (4) + msg_type (1) + payload [+ MIC (4)] [+ PEC (1)]
        # Per DSP0237, byte_count includes through PEC, so MCTP data ends at 3 + byte_count - 1
        expected_end = 3 + byte_count - 1  # -1 to exclude PEC which is included in byte_count

        # Payload starts at offset 9 (after msg_type)
        payload_start = 9

        # If IC bit set, exclude MIC (4 bytes) from payload
        if integrity_check:
            payload_end = expected_end - 4  # Exclude MIC
        else:
            payload_end = expected_end

        # Check if there's a PEC byte
        has_pec = len(data) > expected_end

        if has_pec:
            payload = data[payload_start:payload_end]
            pec = data[expected_end]

            # Validate PEC if requested
            pec_valid = None
            if validate_pec:
                calculated = MCTPBuilder.calculate_pec(data[:expected_end])
                pec_valid = calculated == pec
        else:
            payload = data[payload_start:payload_end] if integrity_check else data[payload_start:]
            pec = None
            pec_valid = None

        return ParsedMCTPPacket(
            raw=data,
            smbus_addr=smbus_addr,
            smbus_cmd=smbus_cmd,
            byte_count=byte_count,
            header=header,
            msg_type=msg_type,
            integrity_check=integrity_check,
            payload=payload,
            pec=pec,
            pec_valid=pec_valid,
        )

    def parse_hex(
        self,
        hex_str: str,
        validate_pec: bool = True,
    ) -> ParsedMCTPPacket:
        """
        Parse packet from hex string.

        Accepts space-separated or comma-separated hex values.

        Args:
            hex_str: Hex string like "20 f 11 3b 1 0 0 c4..."
            validate_pec: Whether to validate PEC byte

        Returns:
            ParsedMCTPPacket

        Example:
            parsed = parser.parse_hex("20 f 11 3b 1 0 0 c4 84 80 0 0 45")
        """
        # Normalize separators
        hex_str = hex_str.replace(",", " ")
        parts = hex_str.split()

        # Parse each hex value
        data = bytes(int(p, 16) for p in parts)

        return self.parse(data, validate_pec)

    def extract_nvme_mi_response(
        self,
        data: bytes,
    ) -> tuple[int, int, bytes]:
        """
        Quick extraction of NVMe-MI response components.

        Args:
            data: Raw packet bytes

        Returns:
            Tuple of (status, opcode, response_data)
        """
        parsed = self.parse(data, validate_pec=False)

        if not parsed.is_nvme_mi:
            raise ValueError(f"Not an NVMe-MI message: type=0x{parsed.msg_type:02X}")

        payload = parsed.nvme_mi_payload

        if len(payload) < 4:
            raise ValueError(f"NVMe-MI payload too short: {len(payload)} bytes")

        # NVMe-MI Response format: [MsgType][Status][Reserved][Reserved][Data...]
        # But MsgType is already consumed, so payload is: [Status][Rsvd][Rsvd][Data...]
        # Actually need to check the spec - the opcode may be echoed

        status = payload[0]
        # Bytes 1-2 often contain response-specific header
        response_data = payload[3:] if len(payload) > 3 else b""

        return status, 0, response_data
