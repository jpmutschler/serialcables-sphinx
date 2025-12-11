"""
MCTP packet builder for constructing properly framed MCTP messages.

Supports fragmentation for payloads exceeding the 128-byte TX packet limit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from serialcables_sphinx.mctp.constants import (
    DEFAULT_SMBUS_ADDRESS,
    DEFAULT_SOURCE_EID,
    MCTP_SMBUS_COMMAND_CODE,
    MCTPMessageType,
)
from serialcables_sphinx.mctp.fragmentation import (
    FragmentationConstants,
    FragmentedMessage,
    MCTPFragment,
)
from serialcables_sphinx.mctp.header import MCTPHeader


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
    smbus_src_addr: int = 0x21  # SMBus source address (host/BMC address)
    src_eid: int = DEFAULT_SOURCE_EID
    auto_pec: bool = True
    _msg_tag: int = field(default=0, repr=False)

    def build_raw(
        self,
        dest_eid: int,
        msg_type: int,
        payload: bytes,
        src_eid: int | None = None,
        som: bool = True,
        eom: bool = True,
        pkt_seq: int = 0,
        msg_tag: int | None = None,
        tag_owner: bool = True,
        smbus_addr: int | None = None,
        include_pec: bool | None = None,
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
        msg_and_payload = bytes([msg_type]) + payload

        # If IC (Integrity Check) bit is set, append CRC-32C MIC
        if msg_type & 0x80:
            mic = self.calculate_crc32c(msg_and_payload)
            msg_and_payload += mic.to_bytes(4, "little")

        mctp_message = header.pack() + msg_and_payload

        # SMBus framing per DSP0237 (MCTP SMBus/I2C Transport Binding)
        # Format: [Dest Addr][Cmd Code][Byte Count][Source Addr][MCTP Data...][PEC]
        # Per DSP0237: Byte Count includes bytes from Source Addr through PEC
        # byte_count = SMBus src (1) + MCTP data + PEC (1 if included)
        pec_size = 1 if include_pec else 0
        byte_count = len(mctp_message) + 1 + pec_size  # +1 for source addr, +1 for PEC
        packet = (
            bytes(
                [
                    smbus_addr,
                    MCTP_SMBUS_COMMAND_CODE,
                    byte_count,
                    self.smbus_src_addr,
                ]
            )
            + mctp_message
        )

        # Add PEC if requested
        if include_pec:
            packet += bytes([self.calculate_pec(packet)])

        return packet

    def build_nvme_mi_request(
        self,
        dest_eid: int,
        payload: bytes,
        integrity_check: bool = True,
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
        msg_type_val = MCTPMessageType.NVME_MI.value
        if integrity_check:
            msg_type_val |= 0x80  # Set IC bit

        return self.build_raw(
            dest_eid=dest_eid,
            msg_type=msg_type_val,
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
        control_header = bytes(
            [
                0x80,  # Rq=1 (request), D=0, InstID=0
                command,
            ]
        )

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

    @staticmethod
    def calculate_crc32c(data: bytes) -> int:
        """
        Calculate CRC-32C (Castagnoli) for NVMe-MI Message Integrity Check.

        Used when IC (Integrity Check) bit is set in message type.

        Args:
            data: Message data (msg_type byte + NVMe-MI payload)

        Returns:
            32-bit CRC-32C value
        """
        # CRC-32C polynomial (Castagnoli), reflected form
        poly = 0x82F63B78
        crc = 0xFFFFFFFF

        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ poly
                else:
                    crc >>= 1

        return crc ^ 0xFFFFFFFF

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

    # -------------------------------------------------------------------------
    # Fragmentation Support
    # -------------------------------------------------------------------------

    def needs_fragmentation(
        self,
        payload: bytes,
        max_payload: int = FragmentationConstants.MAX_TX_PAYLOAD,
    ) -> bool:
        """
        Check if a payload requires fragmentation.

        Args:
            payload: The MCTP payload (message type byte + data)
            max_payload: Maximum payload per packet

        Returns:
            True if payload exceeds single packet limit
        """
        # Account for message type byte in the payload calculation
        # The 'payload' passed to build_raw doesn't include msg_type,
        # but the wire format does
        total_payload = len(payload) + 1  # +1 for message type byte
        return total_payload > max_payload

    def calculate_fragment_count(
        self,
        payload: bytes,
        max_payload: int = FragmentationConstants.MAX_TX_PAYLOAD,
    ) -> int:
        """
        Calculate number of fragments needed for a payload.

        Args:
            payload: The payload bytes (not including message type)
            max_payload: Maximum payload per packet

        Returns:
            Number of fragments required (minimum 1)
        """
        total_payload = len(payload) + 1  # +1 for message type
        if total_payload <= max_payload:
            return 1

        # First fragment includes message type byte
        first_data = max_payload - 1
        remaining = len(payload) - first_data

        # Subsequent fragments are pure data
        additional = (remaining + max_payload - 1) // max_payload
        return 1 + additional

    def build_fragmented(
        self,
        dest_eid: int,
        msg_type: int,
        payload: bytes,
        src_eid: int | None = None,
        msg_tag: int | None = None,
        tag_owner: bool = True,
        smbus_addr: int | None = None,
        include_pec: bool | None = None,
        max_payload: int = FragmentationConstants.MAX_TX_PAYLOAD,
    ) -> FragmentedMessage:
        """
        Build a potentially fragmented MCTP message.

        If the payload fits in a single packet, returns a FragmentedMessage
        with one fragment. Otherwise, splits across multiple packets.

        Args:
            dest_eid: Destination Endpoint ID
            msg_type: MCTP message type
            payload: Message payload (after message type byte)
            src_eid: Source EID (uses instance default if None)
            msg_tag: Message tag (auto-assigned if None)
            tag_owner: Tag owner flag
            smbus_addr: Target SMBus address
            include_pec: Include PEC byte
            max_payload: Maximum payload per packet

        Returns:
            FragmentedMessage with all fragments ready for transmission

        Example:
            # Large VPD read that needs fragmentation
            result = builder.build_fragmented(
                dest_eid=1,
                msg_type=MCTPMessageType.NVME_MI,
                payload=large_vpd_data,
            )

            for fragment in result.fragments:
                transport.send(fragment.data)
                time.sleep(0.005)  # Inter-fragment delay
        """
        # Use defaults
        src_eid = src_eid if src_eid is not None else self.src_eid
        smbus_addr = smbus_addr if smbus_addr is not None else self.smbus_addr
        include_pec = include_pec if include_pec is not None else self.auto_pec

        # Assign message tag
        if msg_tag is None:
            msg_tag = self._msg_tag
            self._msg_tag = (self._msg_tag + 1) & 0x07

        # Full payload on wire = msg_type byte + payload
        wire_payload = bytes([msg_type]) + payload

        # Check if fragmentation needed
        if len(wire_payload) <= max_payload:
            # Single packet
            packet = self._build_fragment_packet(
                dest_eid=dest_eid,
                src_eid=src_eid,
                wire_payload=wire_payload,
                som=True,
                eom=True,
                pkt_seq=0,
                msg_tag=msg_tag,
                tag_owner=tag_owner,
                smbus_addr=smbus_addr,
                include_pec=include_pec,
            )

            fragment = MCTPFragment(
                data=packet,
                sequence=0,
                is_first=True,
                is_last=True,
                payload_offset=0,
                payload_length=len(payload),
            )

            return FragmentedMessage(
                fragments=[fragment],
                total_payload_length=len(payload),
                message_tag=msg_tag,
            )

        # Multiple fragments needed
        fragments: list[MCTPFragment] = []
        offset = 0
        pkt_seq = 0

        while offset < len(wire_payload):
            chunk = wire_payload[offset : offset + max_payload]
            is_first = offset == 0
            is_last = offset + len(chunk) >= len(wire_payload)

            packet = self._build_fragment_packet(
                dest_eid=dest_eid,
                src_eid=src_eid,
                wire_payload=chunk,
                som=is_first,
                eom=is_last,
                pkt_seq=pkt_seq,
                msg_tag=msg_tag,
                tag_owner=tag_owner,
                smbus_addr=smbus_addr,
                include_pec=include_pec,
            )

            # Calculate payload offset (accounting for msg_type in first fragment)
            if is_first:
                payload_offset = 0
                payload_len = len(chunk) - 1  # Minus msg_type byte
            else:
                payload_offset = offset - 1  # -1 for msg_type in first fragment
                payload_len = len(chunk)

            fragment = MCTPFragment(
                data=packet,
                sequence=pkt_seq,
                is_first=is_first,
                is_last=is_last,
                payload_offset=payload_offset,
                payload_length=payload_len,
            )
            fragments.append(fragment)

            offset += len(chunk)
            pkt_seq = (pkt_seq + 1) & 0x03  # Wrap at 4

        return FragmentedMessage(
            fragments=fragments,
            total_payload_length=len(payload),
            message_tag=msg_tag,
        )

    def _build_fragment_packet(
        self,
        dest_eid: int,
        src_eid: int,
        wire_payload: bytes,
        som: bool,
        eom: bool,
        pkt_seq: int,
        msg_tag: int,
        tag_owner: bool,
        smbus_addr: int,
        include_pec: bool,
    ) -> bytes:
        """
        Build a single fragment packet.

        The wire_payload already includes the message type byte for the
        first fragment. Subsequent fragments are continuation data only.
        """
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

        # MCTP message = header + wire_payload (which includes msg_type for first)
        mctp_message = header.pack() + wire_payload

        # SMBus framing (per DSP0237: byte_count includes through PEC)
        pec_size = 1 if include_pec else 0
        byte_count = len(mctp_message) + pec_size
        packet = (
            bytes(
                [
                    smbus_addr,
                    MCTP_SMBUS_COMMAND_CODE,
                    byte_count,
                ]
            )
            + mctp_message
        )

        # Add PEC if requested
        if include_pec:
            packet += bytes([self.calculate_pec(packet)])

        return packet

    def build_nvme_mi_fragmented(
        self,
        dest_eid: int,
        payload: bytes,
        integrity_check: bool = False,
        max_payload: int = FragmentationConstants.MAX_TX_PAYLOAD,
        **kwargs,
    ) -> FragmentedMessage:
        """
        Build a potentially fragmented NVMe-MI request.

        Args:
            dest_eid: Destination Endpoint ID
            payload: NVMe-MI request payload (opcode + parameters)
            integrity_check: Set integrity check flag
            max_payload: Maximum payload per packet
            **kwargs: Additional arguments for build_fragmented

        Returns:
            FragmentedMessage ready for transmission
        """
        msg_type_val = MCTPMessageType.NVME_MI.value
        if integrity_check:
            msg_type_val |= 0x80

        return self.build_fragmented(
            dest_eid=dest_eid,
            msg_type=msg_type_val,
            payload=payload,
            max_payload=max_payload,
            **kwargs,
        )
