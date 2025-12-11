"""
Mock transport for development and testing.

Provides simulated HYDRA device behavior with configurable responses
for NVMe-MI commands. Supports fragmentation for large payloads.

Useful for:
- Development without hardware
- Unit testing
- CI/CD pipelines
- Demonstrating API usage
- Tuning timing parameters to match real hardware

Example:
    from serialcables_sphinx import Sphinx
    from serialcables_sphinx.transports.mock import MockTransport

    # Create mock with default responses
    mock = MockTransport()
    sphinx = Sphinx(mock)

    # Use normally
    result = sphinx.nvme_mi.health_status_poll(eid=1)
    print(result.pretty_print())

    # Check what was sent
    print(f"Packets sent: {len(mock.sent_packets)}")
    print(f"Last TX: {mock.sent_packets[-1].hex(' ')}")
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field
from typing import Callable

from serialcables_sphinx.mctp.builder import MCTPBuilder
from serialcables_sphinx.mctp.constants import MCTP_SMBUS_COMMAND_CODE
from serialcables_sphinx.mctp.fragmentation import (
    FragmentationConstants,
    MessageReassembler,
    PacketSequence,
)
from serialcables_sphinx.nvme_mi.constants import NVMeDataStructureType
from serialcables_sphinx.nvme_mi.opcodes import NVMeMIOpcode
from serialcables_sphinx.nvme_mi.status import NVMeMIStatus
from serialcables_sphinx.transports.base import FragmentedTransportMixin


@dataclass
class MockDeviceState:
    """
    Simulated NVMe device state.

    Modify these values to simulate different device conditions.
    """

    # Health status
    temperature_kelvin: int = 318  # 45°C
    available_spare: int = 100  # 100%
    spare_threshold: int = 10  # 10%
    life_used: int = 5  # 5%
    critical_warning: int = 0x00  # No warnings

    # Controller status
    ready: bool = True
    fatal_status: bool = False
    shutdown_status: int = 0  # Normal operation

    # Subsystem info
    num_ports: int = 1
    nvme_mi_major: int = 1
    nvme_mi_minor: int = 2
    optional_commands: int = 0x1F  # Support config, VPD, reset

    # Controllers
    controller_ids: list[int] = field(default_factory=lambda: [0, 1])

    # Port info
    port_type: int = 0x02  # SMBus/I2C
    max_mctp_mtu: int = 64
    meb_size: int = 4096

    # VPD - can be set to large value to test fragmented responses
    vpd_data: bytes = b"Serial Cables HYDRA Test Device\x00"

    # Response timing (tune to match real hardware)
    response_delay_ms: float = 0.0

    # Fragmentation timing
    inter_fragment_delay_ms: float = 1.0  # Delay between response fragments
    fragment_jitter_ms: float = 0.5  # Random jitter on timing

    # Large data simulation
    large_log_page: bytes = b""  # For testing fragmented responses


@dataclass
class FragmentTiming:
    """Timing data for a fragment exchange."""

    fragment_index: int
    is_first: bool
    is_last: bool
    pkt_seq: int
    tx_size: int
    rx_size: int
    latency_ms: float
    timestamp: float


class MockTransport(FragmentedTransportMixin):
    """
    Mock MCTP transport that simulates HYDRA device behavior.

    Provides configurable responses for NVMe-MI commands and
    records all sent packets for verification in tests.

    Supports message fragmentation for:
    - TX: Reassembles multi-fragment requests before processing
    - RX: Can generate fragmented responses for large data

    Attributes:
        state: Simulated device state (modify for different scenarios)
        sent_packets: List of all packets sent via send_packet()
        response_log: List of (request, response) tuples
        fail_next: If True, next send_packet() raises an error
        custom_handlers: Dict mapping opcodes to custom response generators

    Example:
        mock = MockTransport()

        # Simulate low spare capacity warning
        mock.state.available_spare = 5
        mock.state.critical_warning = 0x01  # Spare below threshold

        sphinx = Sphinx(mock)
        result = sphinx.nvme_mi.health_status_poll(eid=1)
        # Result will show warning condition
    """

    def __init__(
        self,
        state: MockDeviceState | None = None,
        verbose: bool = False,
    ):
        """
        Initialize mock transport.

        Args:
            state: Initial device state (uses defaults if None)
            verbose: Print packets as they're sent/received
        """
        FragmentedTransportMixin.__init__(self)

        self.state = state or MockDeviceState()
        self.verbose = verbose

        # Tracking
        self.sent_packets: list[bytes] = []
        self.response_log: list[tuple[bytes, bytes]] = []
        self.fragment_timings: list[FragmentTiming] = []

        # Error injection
        self.fail_next: bool = False
        self.fail_message: str = "Simulated transport error"

        # Custom response handlers
        self.custom_handlers: dict[int, Callable[[bytes, int], bytes]] = {}

        # Current slot selection
        self._current_slot: int | None = None
        self._current_address: int | None = None

        # Fragment reassembly for incoming requests
        self._reassembler = MessageReassembler()
        self._pending_request: bytes | None = None

        # Response fragmentation state
        self._response_pkt_seq = PacketSequence()

    def send_packet(self, packet: bytes) -> bytes:
        """
        Process packet and return simulated response.

        Handles both single packets and fragmented messages.
        For fragmented requests, buffers until complete before responding.

        Args:
            packet: Complete MCTP packet bytes

        Returns:
            Simulated response bytes

        Raises:
            RuntimeError: If fail_next is True
        """
        start_time = time.perf_counter()

        # Record sent packet
        self.sent_packets.append(packet)

        if self.verbose:
            print(f"[MockTransport] TX: {packet.hex(' ')}")

        # Error injection
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError(self.fail_message)

        # Check for fragmented request
        # With SMBus src addr at offset 3, flags_tag is at offset 7
        if len(packet) >= 8:
            flags_tag = packet[7]
            som = bool(flags_tag & 0x80)
            eom = bool(flags_tag & 0x40)
            pkt_seq = (flags_tag >> 4) & 0x03
            msg_tag = flags_tag & 0x07

            # Track fragment timing
            timing = FragmentTiming(
                fragment_index=len(self.fragment_timings),
                is_first=som,
                is_last=eom,
                pkt_seq=pkt_seq,
                tx_size=len(packet),
                rx_size=0,  # Updated after response
                latency_ms=0,
                timestamp=time.time(),
            )

            if not (som and eom):
                # Multi-fragment message
                if self.verbose:
                    frag_type = "FIRST" if som else ("LAST" if eom else "MIDDLE")
                    print(f"[MockTransport] Fragment: {frag_type} (seq={pkt_seq})")

                # Extract payload for reassembly
                # byte_count includes SMBus src addr, so payload starts after MCTP header
                byte_count = packet[2]
                msg_type_offset = 8  # After SMBus(4) + MCTP header(4)
                payload = packet[msg_type_offset : 3 + byte_count]  # Before PEC

                try:
                    src_eid = packet[6]
                    complete = self._reassembler.process_fragment(
                        payload=payload,
                        msg_tag=msg_tag,
                        src_eid=src_eid,
                        pkt_seq=pkt_seq,
                        som=som,
                        eom=eom,
                    )

                    if complete is not None:
                        # Got complete message - process it
                        if self.verbose:
                            print(f"[MockTransport] Reassembled: {len(complete)} bytes")

                        # Reconstruct a "complete" packet for processing
                        # Keep original SMBus + MCTP header but with reassembled payload
                        reconstructed = packet[:8] + complete
                        response = self._generate_response(reconstructed)

                        timing.rx_size = len(response)
                        timing.latency_ms = (time.perf_counter() - start_time) * 1000
                        self.fragment_timings.append(timing)

                        self.response_log.append((packet, response))

                        if self.verbose:
                            print(f"[MockTransport] RX: {response.hex(' ')}")

                        return response
                    else:
                        # Still waiting for more fragments
                        # Return empty ACK
                        timing.rx_size = 0
                        timing.latency_ms = (time.perf_counter() - start_time) * 1000
                        self.fragment_timings.append(timing)

                        return b""  # No response until complete

                except ValueError as e:
                    if self.verbose:
                        print(f"[MockTransport] Reassembly error: {e}")
                    return self._build_error_response(0x00, NVMeMIStatus.MESSAGE_FORMAT_ERROR)

        # Simulate response delay
        if self.state.response_delay_ms > 0:
            time.sleep(self.state.response_delay_ms / 1000.0)

        # Parse request and generate response
        response = self._generate_response(packet)

        # Record exchange
        self.response_log.append((packet, response))

        elapsed = (time.perf_counter() - start_time) * 1000

        if self.verbose:
            print(f"[MockTransport] RX: {response.hex(' ')} ({elapsed:.2f}ms)")

        return response

    def set_target(
        self,
        slot: int | None = None,
        address: int | None = None,
    ) -> None:
        """
        Set target slot/address (simulated mux routing).

        Args:
            slot: Slot number
            address: Bus address
        """
        if slot is not None:
            self._current_slot = slot
            if self.verbose:
                print(f"[MockTransport] Selected slot {slot}")

        if address is not None:
            self._current_address = address
            if self.verbose:
                print(f"[MockTransport] Set address 0x{address:02X}")

    def _generate_response(self, packet: bytes) -> bytes:
        """Generate simulated response for request packet."""
        # Parse MCTP-over-SMBus framing
        # Format: [SMBus dest][Cmd code][Byte count][SMBus src][MCTP header...][Msg type][Payload][MIC?][PEC]
        if len(packet) < 13:
            return self._build_error_response(0x00, NVMeMIStatus.MESSAGE_FORMAT_ERROR)

        # smbus_dest = packet[0]  # 0x3A for NVMe-MI
        # smbus_cmd = packet[1]   # Should be 0x0F
        byte_count = packet[2]
        # smbus_src = packet[3]   # 0x21 for host

        # MCTP header at offset 4-7
        # header_version = packet[4] & 0x0F
        dest_eid = packet[5]
        src_eid = packet[6]
        flags_tag = packet[7]

        # Message type at offset 8 (IC bit is bit 7)
        msg_type_byte = packet[8]
        msg_type = msg_type_byte & 0x7F
        has_ic = bool(msg_type_byte & 0x80)  # Integrity Check bit

        # For NVMe-MI (type 0x04), extract opcode
        if msg_type != 0x04:
            # Not NVMe-MI, return generic error
            return self._build_error_response(0x00, NVMeMIStatus.INVALID_OPCODE)

        # Calculate payload end (exclude MIC if present, exclude PEC)
        # byte_count includes SMBus src byte and PEC, so actual MCTP data ends at 3 + byte_count - 1 (before PEC)
        payload_end = 3 + byte_count - 1  # Before PEC (since byte_count includes PEC per DSP0237)
        if has_ic:
            payload_end -= 4  # Exclude 4-byte MIC

        # NVMe-MI payload starts at offset 9
        # Format per HYDRA firmware: [NMIMT/ROR][Reserved][Reserved][Opcode][Data...][Flags]
        # NMIMT/ROR byte: bits 7=ROR (0=request), bits 3:0=NMIMT (8 for MI Command per HYDRA)
        if len(packet) < 13:
            return self._build_error_response(0x00, NVMeMIStatus.INVALID_COMMAND_SIZE)

        # nmimt_ror = packet[9]   # 0x08 for MI Command per HYDRA
        # reserved = packet[10:12]  # Two reserved bytes
        opcode = packet[12]  # Opcode at byte 3 of NVMe-MI payload (offset 9+3=12)
        # Request data starts at offset 13 (after NMIMT/ROR, reserved x2, opcode)
        request_data = packet[13:payload_end] if payload_end > 13 else b""

        # Check for custom handler
        if opcode in self.custom_handlers:
            response_payload = self.custom_handlers[opcode](request_data, dest_eid)
        else:
            # Use built-in handlers
            response_payload = self._handle_opcode(opcode, request_data)

        # Build complete MCTP response (mirror IC bit from request)
        return self._build_mctp_response(
            response_payload,
            src_eid=dest_eid,  # Swap for response
            dest_eid=src_eid,
            msg_tag=flags_tag & 0x07,
            smbus_addr=0x20,  # Response address (host)
            integrity_check=has_ic,  # Mirror IC bit from request
        )

    def _handle_opcode(self, opcode: int, data: bytes) -> bytes:
        """Route opcode to appropriate handler."""
        handlers = {
            NVMeMIOpcode.READ_NVME_MI_DATA_STRUCTURE: self._handle_read_data_structure,
            NVMeMIOpcode.NVM_SUBSYSTEM_HEALTH_STATUS_POLL: self._handle_health_status,
            NVMeMIOpcode.CONTROLLER_HEALTH_STATUS_POLL: self._handle_controller_health,
            NVMeMIOpcode.CONFIGURATION_GET: self._handle_config_get,
            NVMeMIOpcode.CONFIGURATION_SET: self._handle_config_set,
            NVMeMIOpcode.VPD_READ: self._handle_vpd_read,
            NVMeMIOpcode.MI_RESET: self._handle_mi_reset,
        }

        handler = handlers.get(opcode)
        if handler:
            return handler(data)

        # Unknown opcode
        return self._build_mi_response(NVMeMIStatus.INVALID_OPCODE, b"")

    def _handle_health_status(self, data: bytes) -> bytes:
        """Generate NVM Subsystem Health Status Poll response."""
        s = self.state

        # Build CCS byte
        ccs = (int(s.ready) << 0) | (int(s.fatal_status) << 1) | ((s.shutdown_status & 0x03) << 2)

        # Response: [CCS][CW][Temp_L][Temp_H][LifeUsed][SpareThresh][Spare]
        payload = struct.pack(
            "<BBHBBB",
            ccs,
            s.critical_warning,
            s.temperature_kelvin,
            s.life_used,
            s.spare_threshold,
            s.available_spare,
        )

        return self._build_mi_response(NVMeMIStatus.SUCCESS, payload)

    def _handle_controller_health(self, data: bytes) -> bytes:
        """Generate Controller Health Status Poll response."""
        s = self.state

        # Parse controller ID from request
        ctrl_id = struct.unpack("<H", data[0:2])[0] if len(data) >= 2 else 0

        # Check if controller exists
        if ctrl_id not in s.controller_ids:
            return self._build_mi_response(NVMeMIStatus.INVALID_PARAMETER, b"")

        # Build controller status byte
        csts = (int(s.ready) << 0) | (int(s.fatal_status) << 1) | ((s.shutdown_status & 0x03) << 2)

        # Response format per spec
        payload = struct.pack(
            "<HBBHHHHBBB",
            ctrl_id,
            csts,
            0,  # Reserved
            s.temperature_kelvin,
            s.temperature_kelvin + 20,  # Warning threshold (65°C above)
            s.temperature_kelvin + 40,  # Critical threshold (85°C above)
            0,  # Reserved
            s.available_spare,
            s.spare_threshold,
            s.life_used,
        )

        return self._build_mi_response(NVMeMIStatus.SUCCESS, payload)

    def _handle_read_data_structure(self, data: bytes) -> bytes:
        """Generate Read NVMe-MI Data Structure response."""
        if len(data) < 1:
            return self._build_mi_response(NVMeMIStatus.INVALID_PARAMETER, b"")

        data_type = data[0]
        s = self.state

        if data_type == NVMeDataStructureType.NVM_SUBSYSTEM_INFORMATION:
            # Subsystem info
            payload = struct.pack(
                "<BBBBI",
                s.num_ports,
                s.nvme_mi_major,
                s.nvme_mi_minor,
                0,  # Reserved
                s.optional_commands,
            )

        elif data_type == NVMeDataStructureType.CONTROLLER_LIST:
            # Controller list
            num_ctrls = len(s.controller_ids)
            payload = struct.pack("<BB", num_ctrls, 0)  # Count + reserved
            for ctrl_id in s.controller_ids:
                payload += struct.pack("<H", ctrl_id)

        elif data_type == NVMeDataStructureType.PORT_INFORMATION:
            # Port info
            payload = struct.pack(
                "<BBHI",
                s.port_type,
                0,  # Reserved
                s.max_mctp_mtu,
                s.meb_size,
            )

        elif data_type == NVMeDataStructureType.CONTROLLER_INFORMATION:
            # Controller info (simplified)
            ctrl_id = data[1] if len(data) > 1 else 0
            if ctrl_id not in s.controller_ids:
                return self._build_mi_response(NVMeMIStatus.INVALID_PARAMETER, b"")
            payload = struct.pack("<HBB", ctrl_id, 0x01, 0x00)  # Minimal info

        else:
            return self._build_mi_response(NVMeMIStatus.INVALID_PARAMETER, b"")

        return self._build_mi_response(NVMeMIStatus.SUCCESS, payload)

    def _handle_config_get(self, data: bytes) -> bytes:
        """Generate Configuration Get response."""
        if len(data) < 1:
            return self._build_mi_response(NVMeMIStatus.INVALID_PARAMETER, b"")

        config_id = data[0]

        # Return some default config values
        if config_id == 0x01:  # SMBus/I2C frequency
            payload = struct.pack("<I", 400000)  # 400 kHz
        elif config_id == 0x02:  # Health status change
            payload = struct.pack("<I", 0)
        elif config_id == 0x03:  # MCTP MTU
            payload = struct.pack("<H", self.state.max_mctp_mtu)
        else:
            return self._build_mi_response(NVMeMIStatus.INVALID_PARAMETER, b"")

        return self._build_mi_response(NVMeMIStatus.SUCCESS, payload)

    def _handle_config_set(self, data: bytes) -> bytes:
        """Generate Configuration Set response."""
        # Just acknowledge success
        return self._build_mi_response(NVMeMIStatus.SUCCESS, b"")

    def _handle_vpd_read(self, data: bytes) -> bytes:
        """Generate VPD Read response."""
        s = self.state

        # Parse offset and length from request
        offset = struct.unpack("<H", data[0:2])[0] if len(data) >= 2 else 0
        length = struct.unpack("<H", data[2:4])[0] if len(data) >= 4 else 256

        # Get VPD slice
        vpd_slice = s.vpd_data[offset : offset + length]

        # Response: [Length (2)][Data...]
        payload = struct.pack("<H", len(vpd_slice)) + vpd_slice

        return self._build_mi_response(NVMeMIStatus.SUCCESS, payload)

    def _handle_mi_reset(self, data: bytes) -> bytes:
        """Generate MI Reset response."""
        # Reset state to defaults
        self.state.ready = True
        self.state.fatal_status = False
        self.state.shutdown_status = 0

        return self._build_mi_response(NVMeMIStatus.SUCCESS, b"")

    def _build_mi_response(self, status: int, payload: bytes) -> bytes:
        """
        Build NVMe-MI response payload.

        Format: [ResponseType][Status][Reserved][Reserved][Payload...]
        """
        return (
            bytes(
                [
                    0x02,  # MI Response type
                    status,
                    0x00,  # Reserved
                    0x00,  # Reserved
                ]
            )
            + payload
        )

    def _build_error_response(self, opcode: int, status: int) -> bytes:
        """Build error response for given status."""
        mi_response = self._build_mi_response(status, b"")
        return self._build_mctp_response(mi_response)

    def _build_mctp_response(
        self,
        payload: bytes,
        src_eid: int = 1,
        dest_eid: int = 0,
        msg_tag: int = 0,
        smbus_addr: int = 0x20,
        integrity_check: bool = False,
    ) -> bytes:
        """
        Build complete MCTP-over-SMBus response.

        Automatically uses fragmentation if payload exceeds RX limit.
        For fragmented responses, returns only the first fragment
        (caller should handle multi-fragment retrieval in real implementation).

        Args:
            payload: NVMe-MI response payload (including MI header)
            src_eid: Source EID (device)
            dest_eid: Destination EID (host)
            msg_tag: Message tag from request
            smbus_addr: Response SMBus address
            integrity_check: Include IC bit and MIC in response

        Returns:
            Complete MCTP packet bytes (first fragment if fragmented)
        """
        # Check if payload fits in single packet
        # Payload + msg_type byte + MCTP header (4) + optional MIC (4) must fit
        mic_size = 4 if integrity_check else 0
        max_single_payload = FragmentationConstants.MAX_RX_PAYLOAD - 1 - mic_size

        if len(payload) > max_single_payload:
            # Need fragmented response
            fragments = self._build_fragmented_response(
                payload=payload,
                src_eid=src_eid,
                dest_eid=dest_eid,
                msg_tag=msg_tag,
                smbus_addr=smbus_addr,
                integrity_check=integrity_check,
            )

            if self.verbose:
                print(f"[MockTransport] Response requires {len(fragments)} fragments")

            # For now, return concatenated fragments
            # Real hardware would require multiple reads
            # This simulates the full reassembled response
            return fragments[0] if len(fragments) == 1 else b"".join(fragments)

        # Standard single-packet response
        # MCTP header
        header_byte0 = 0x01  # Version
        flags_tag = 0xC0 | msg_tag  # SOM=1, EOM=1, TO=0, Tag

        mctp_header = bytes([header_byte0, dest_eid, src_eid, flags_tag])

        # Message type (NVMe-MI = 0x04, with IC bit if integrity check)
        msg_type = 0x84 if integrity_check else 0x04

        # Build message payload (msg_type + payload)
        msg_and_payload = bytes([msg_type]) + payload

        # Add MIC if integrity check enabled
        if integrity_check:
            mic = MCTPBuilder.calculate_crc32c(msg_and_payload)
            msg_and_payload += mic.to_bytes(4, "little")

        # Full MCTP message
        mctp_message = mctp_header + msg_and_payload

        # SMBus framing (per DSP0237: byte_count includes through PEC)
        # Format: [Dest Addr][Cmd Code][Byte Count][Source Addr][MCTP Data...][PEC]
        smbus_src_addr = 0x3B  # Device SMBus source address (mirroring HYDRA)
        byte_count = len(mctp_message) + 1 + 1  # +1 for SMBus src, +1 for PEC
        packet = (
            bytes(
                [
                    smbus_addr,
                    MCTP_SMBUS_COMMAND_CODE,
                    byte_count,
                    smbus_src_addr,
                ]
            )
            + mctp_message
        )

        # Add PEC
        pec = MCTPBuilder.calculate_pec(packet)
        packet += bytes([pec])

        return packet

    def _build_fragmented_response(
        self,
        payload: bytes,
        src_eid: int = 1,
        dest_eid: int = 0,
        msg_tag: int = 0,
        smbus_addr: int = 0x20,
        max_payload: int = FragmentationConstants.MAX_RX_PAYLOAD,
        integrity_check: bool = False,
    ) -> list[bytes]:
        """
        Build fragmented MCTP response for large payloads.

        Splits response into multiple fragments that fit within RX limit.

        Args:
            payload: Complete NVMe-MI response payload
            src_eid: Source EID (device)
            dest_eid: Destination EID (host)
            msg_tag: Message tag from request
            smbus_addr: Response SMBus address
            max_payload: Max payload per fragment

        Returns:
            List of MCTP packet fragments
        """
        # Message type byte is part of the payload on wire (with IC bit if enabled)
        msg_type = 0x84 if integrity_check else 0x04  # NVMe-MI
        wire_payload = bytes([msg_type]) + payload

        # Add MIC if integrity check enabled (only on the full message)
        if integrity_check:
            mic = MCTPBuilder.calculate_crc32c(wire_payload)
            wire_payload += mic.to_bytes(4, "little")

        if len(wire_payload) <= max_payload:
            # Fits in single packet
            return [
                self._build_mctp_response(
                    payload, src_eid, dest_eid, msg_tag, smbus_addr, integrity_check
                )
            ]

        fragments = []
        self._response_pkt_seq.reset()
        offset = 0

        while offset < len(wire_payload):
            chunk = wire_payload[offset : offset + max_payload]
            is_first = offset == 0
            is_last = offset + len(chunk) >= len(wire_payload)
            pkt_seq = self._response_pkt_seq.next()

            # Build flags byte: SOM, EOM, pkt_seq, TO=0, msg_tag
            flags_tag = msg_tag & 0x07  # Tag in lower 3 bits
            if is_first:
                flags_tag |= 0x80  # SOM
            if is_last:
                flags_tag |= 0x40  # EOM
            flags_tag |= pkt_seq << 4  # Packet sequence

            # MCTP header
            mctp_header = bytes([0x01, dest_eid, src_eid, flags_tag])

            # For first fragment, chunk includes msg_type
            # For subsequent fragments, chunk is continuation data
            mctp_message = mctp_header + chunk

            # SMBus framing (per DSP0237: byte_count includes through PEC)
            # Format: [Dest Addr][Cmd Code][Byte Count][Source Addr][MCTP Data...][PEC]
            smbus_src_addr = 0x3B  # Device SMBus source address
            byte_count = len(mctp_message) + 1 + 1  # +1 for SMBus src, +1 for PEC
            packet = (
                bytes(
                    [
                        smbus_addr,
                        MCTP_SMBUS_COMMAND_CODE,
                        byte_count,
                        smbus_src_addr,
                    ]
                )
                + mctp_message
            )

            # Add PEC
            pec = MCTPBuilder.calculate_pec(packet)
            packet += bytes([pec])

            fragments.append(packet)
            offset += len(chunk)

        if self.verbose:
            print(f"[MockTransport] Generated {len(fragments)} response fragments")

        return fragments

    def set_large_vpd(self, size: int = 512) -> None:
        """
        Set VPD to a large value to test fragmented responses.

        Args:
            size: Total VPD size in bytes
        """
        # Generate test VPD data
        vpd = b"Serial Cables HYDRA - Large VPD Test\n"
        vpd += b"=" * 40 + b"\n"

        # Fill with structured data
        while len(vpd) < size:
            remaining = size - len(vpd)
            line = f"VPD Offset 0x{len(vpd):04X}: Test data block\n".encode()
            if len(line) > remaining:
                vpd += b"X" * remaining
            else:
                vpd += line

        self.state.vpd_data = vpd[:size]

    def get_timing_summary(self) -> dict:
        """
        Get summary of fragment timing data.

        Returns:
            Dict with min/max/avg latencies and fragment counts
        """
        if not self.fragment_timings:
            return {
                "fragment_count": 0,
                "min_latency_ms": 0,
                "max_latency_ms": 0,
                "avg_latency_ms": 0,
            }

        latencies = [t.latency_ms for t in self.fragment_timings]

        return {
            "fragment_count": len(self.fragment_timings),
            "min_latency_ms": min(latencies),
            "max_latency_ms": max(latencies),
            "avg_latency_ms": sum(latencies) / len(latencies),
            "total_tx_bytes": sum(t.tx_size for t in self.fragment_timings),
            "total_rx_bytes": sum(t.rx_size for t in self.fragment_timings),
        }

    # =========================================================================
    # Test Helpers
    # =========================================================================

    def reset(self) -> None:
        """Reset tracking state (keeps device state)."""
        self.sent_packets.clear()
        self.response_log.clear()
        self.fragment_timings.clear()
        self.fail_next = False
        self._reassembler.reset()

    def reset_all(self) -> None:
        """Reset everything including device state."""
        self.reset()
        self.state = MockDeviceState()

    def get_last_request(self) -> bytes | None:
        """Get the last packet sent."""
        return self.sent_packets[-1] if self.sent_packets else None

    def get_last_opcode(self) -> int | None:
        """Extract opcode from last request."""
        if not self.sent_packets:
            return None
        packet = self.sent_packets[-1]
        # Opcode is at offset 12 per HYDRA firmware format:
        # [0-2]=SMBus header, [3]=SMBus src, [4-7]=MCTP header, [8]=MsgType,
        # [9]=NMIMT/ROR, [10-11]=Reserved, [12]=Opcode
        if len(packet) >= 13:
            return packet[12]
        return None

    def inject_error(self, message: str = "Simulated transport error") -> None:
        """Make next send_packet() raise an error."""
        self.fail_next = True
        self.fail_message = message

    def register_handler(
        self,
        opcode: int,
        handler: Callable[[bytes, int], bytes],
    ) -> None:
        """
        Register custom response handler for an opcode.

        Args:
            opcode: NVMe-MI opcode to handle
            handler: Function(request_data, dest_eid) -> response_payload
        """
        self.custom_handlers[opcode] = handler

    def set_temperature(self, celsius: int) -> None:
        """Convenience: set device temperature in Celsius."""
        self.state.temperature_kelvin = celsius + 273

    def set_warning_condition(self) -> None:
        """Set device to warning state (low spare, high temp)."""
        self.state.available_spare = 5
        self.state.critical_warning = 0x03  # Spare + temp warnings
        self.state.temperature_kelvin = 358  # 85°C

    def set_critical_condition(self) -> None:
        """Set device to critical state."""
        self.state.fatal_status = True
        self.state.critical_warning = 0x0F
        self.state.available_spare = 0
        self.state.life_used = 100


# Convenience aliases
MockHYDRA = MockTransport
MockHYDRADevice = MockTransport
