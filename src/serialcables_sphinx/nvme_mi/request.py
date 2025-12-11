"""
NVMe-MI request message builder.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from serialcables_sphinx.nvme_mi.constants import (
    ConfigurationIdentifier,
    NVMeDataStructureType,
)
from serialcables_sphinx.nvme_mi.opcodes import NVMeMIOpcode


@dataclass
class NVMeMIRequest:
    """
    NVMe-MI Request Message builder.

    Builds the NVMe-MI request payload that goes inside an MCTP packet.
    The message type byte (0x04 for NVMe-MI) is handled by MCTP builder.

    Attributes:
        opcode: MI command opcode
        data: Command-specific request data

    Example:
        # Health status poll (no additional data)
        req = NVMeMIRequest(opcode=NVMeMIOpcode.NVM_SUBSYSTEM_HEALTH_STATUS_POLL)

        # Read data structure with type parameter
        req = NVMeMIRequest.read_data_structure(
            NVMeDataStructureType.CONTROLLER_LIST
        )
    """

    opcode: int | NVMeMIOpcode
    data: bytes = b""

    def pack(self, min_length: int = 14) -> bytes:
        """
        Pack request into bytes for MCTP payload.

        Format (per HYDRA firmware packet capture):
            Byte 0: NMIMT/ROR (NVMe-MI Message Type / Request or Response)
                    Bits 7: ROR (0=Request, 1=Response)
                    Bits 6:4: Reserved
                    Bits 3:0: NMIMT (8 for MI Command Set per HYDRA)
            Bytes 1-2: Reserved (zeros)
            Byte 3: Opcode
            Bytes 4+: Command-specific request data
            Byte 13: Flags (0x80 observed in firmware packets)

        The firmware uses a 14-byte minimum payload with specific structure.

        Args:
            min_length: Minimum payload length (default 14 to match firmware)

        Returns:
            Request payload bytes (padded to min_length)
        """
        opcode_val = self.opcode.value if isinstance(self.opcode, NVMeMIOpcode) else self.opcode

        # NVMe-MI Request per HYDRA firmware format:
        # [NMIMT/ROR][Reserved][Reserved][Opcode][Data...][Flags]
        # HYDRA uses NMIMT=0x08 for MI commands
        nmimt_ror = 0x08

        # Build header: NMIMT + 2 reserved + Opcode
        header = bytes([nmimt_ror, 0x00, 0x00, opcode_val])

        # Add command-specific data
        payload = header + self.data

        # Pad to minimum length (firmware uses 14 bytes)
        # The last byte (byte 13) is 0x80 in firmware captures
        if len(payload) < min_length:
            # Pad with zeros, but set last byte to 0x80 like firmware
            padding_needed = min_length - len(payload)
            if padding_needed > 0:
                payload = payload + bytes(padding_needed - 1) + bytes([0x80])

        return payload

    @classmethod
    def health_status_poll(cls) -> NVMeMIRequest:
        """
        Create NVM Subsystem Health Status Poll request.

        Returns:
            Request for opcode 0x01
        """
        return cls(opcode=NVMeMIOpcode.NVM_SUBSYSTEM_HEALTH_STATUS_POLL)

    @classmethod
    def controller_health_status(cls, controller_id: int) -> NVMeMIRequest:
        """
        Create Controller Health Status Poll request.

        Args:
            controller_id: Target controller ID

        Returns:
            Request for opcode 0x02
        """
        # Controller ID in DWORD 0 of request data
        data = struct.pack("<H", controller_id) + b"\x00\x00"
        return cls(opcode=NVMeMIOpcode.CONTROLLER_HEALTH_STATUS_POLL, data=data)

    @classmethod
    def read_data_structure(
        cls,
        data_type: int | NVMeDataStructureType,
        port_id: int = 0,
        controller_id: int = 0,
    ) -> NVMeMIRequest:
        """
        Create Read NVMe-MI Data Structure request.

        Args:
            data_type: Type of data structure to read
            port_id: Port ID (for PORT_INFORMATION type)
            controller_id: Controller ID (for CONTROLLER_INFORMATION type)

        Returns:
            Request for opcode 0x00
        """
        type_val = data_type.value if isinstance(data_type, NVMeDataStructureType) else data_type

        # Determine which ID to use based on data type
        if data_type == NVMeDataStructureType.PORT_INFORMATION:
            id_field = port_id
        elif data_type == NVMeDataStructureType.CONTROLLER_INFORMATION:
            id_field = controller_id
        else:
            id_field = 0

        # Data: [Type (1)][Port/Ctrl ID (1)][Reserved (2)]
        data = bytes([type_val, id_field, 0x00, 0x00])

        return cls(opcode=NVMeMIOpcode.READ_NVME_MI_DATA_STRUCTURE, data=data)

    @classmethod
    def configuration_get(
        cls,
        config_id: int | ConfigurationIdentifier,
        port_id: int = 0,
    ) -> NVMeMIRequest:
        """
        Create Configuration Get request.

        Args:
            config_id: Configuration identifier
            port_id: Port ID (for port-specific configurations)

        Returns:
            Request for opcode 0x04
        """
        id_val = config_id.value if isinstance(config_id, ConfigurationIdentifier) else config_id

        # Data: [Config ID (1)][Port ID (1)][Reserved (2)]
        data = bytes([id_val, port_id, 0x00, 0x00])

        return cls(opcode=NVMeMIOpcode.CONFIGURATION_GET, data=data)

    @classmethod
    def configuration_set(
        cls,
        config_id: int | ConfigurationIdentifier,
        config_data: bytes,
        port_id: int = 0,
    ) -> NVMeMIRequest:
        """
        Create Configuration Set request.

        Args:
            config_id: Configuration identifier
            config_data: Configuration value data
            port_id: Port ID (for port-specific configurations)

        Returns:
            Request for opcode 0x03
        """
        id_val = config_id.value if isinstance(config_id, ConfigurationIdentifier) else config_id

        # Data: [Config ID (1)][Port ID (1)][Reserved (2)][Config Data...]
        data = bytes([id_val, port_id, 0x00, 0x00]) + config_data

        return cls(opcode=NVMeMIOpcode.CONFIGURATION_SET, data=data)

    @classmethod
    def vpd_read(
        cls,
        offset: int = 0,
        length: int = 256,
    ) -> NVMeMIRequest:
        """
        Create VPD Read request.

        Args:
            offset: Byte offset into VPD data
            length: Number of bytes to read

        Returns:
            Request for opcode 0x05
        """
        # Data: [Offset (2)][Length (2)]
        data = struct.pack("<HH", offset, length)

        return cls(opcode=NVMeMIOpcode.VPD_READ, data=data)

    @classmethod
    def mi_reset(cls) -> NVMeMIRequest:
        """
        Create MI Reset request.

        Returns:
            Request for opcode 0x07
        """
        return cls(opcode=NVMeMIOpcode.MI_RESET)

    @classmethod
    def vendor_specific(cls, opcode: int, data: bytes = b"") -> NVMeMIRequest:
        """
        Create vendor-specific request.

        Args:
            opcode: Vendor opcode (0xC0-0xFF)
            data: Vendor-specific data

        Returns:
            Request with vendor opcode
        """
        if not NVMeMIOpcode.is_vendor_specific(opcode):
            raise ValueError(f"Vendor opcode must be 0xC0-0xFF, got 0x{opcode:02X}")

        return cls(opcode=opcode, data=data)

    def __str__(self) -> str:
        opcode_str = NVMeMIOpcode.decode(
            self.opcode.value if isinstance(self.opcode, NVMeMIOpcode) else self.opcode
        )
        return f"NVMeMIRequest({opcode_str}, data={self.data.hex()})"
