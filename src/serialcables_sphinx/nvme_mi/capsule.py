"""
NVMe-MI Command Capsule support for Admin command tunneling.

Supports both NVMe-MI 1.2 (MI Send/MI Receive) and NVMe-MI 2.x (Command Capsule) formats.

Reference:
    - NVMe-MI 1.2, Section 6.7 (MI Send), Section 6.8 (MI Receive)
    - NVMe-MI 2.0, Section 5.3 (Command Capsule Format)
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class AdminOpcode(IntEnum):
    """
    NVMe Admin Command Opcodes commonly tunneled through NVMe-MI.

    Reference: NVMe Base Specification
    """

    DELETE_IO_SQ = 0x00
    CREATE_IO_SQ = 0x01
    GET_LOG_PAGE = 0x02
    DELETE_IO_CQ = 0x04
    CREATE_IO_CQ = 0x05
    IDENTIFY = 0x06
    ABORT = 0x08
    SET_FEATURES = 0x09
    GET_FEATURES = 0x0A
    ASYNC_EVENT_REQUEST = 0x0C
    NS_MANAGEMENT = 0x0D
    FW_COMMIT = 0x10
    FW_IMAGE_DOWNLOAD = 0x11
    DEVICE_SELF_TEST = 0x14
    NS_ATTACHMENT = 0x15
    KEEP_ALIVE = 0x18
    DIRECTIVE_SEND = 0x19
    DIRECTIVE_RECEIVE = 0x1A
    VIRTUALIZATION_MGMT = 0x1C
    NVME_MI_SEND = 0x1D
    NVME_MI_RECEIVE = 0x1E
    DOORBELL_BUFFER_CONFIG = 0x7C
    FORMAT_NVM = 0x80
    SECURITY_SEND = 0x81
    SECURITY_RECEIVE = 0x82
    SANITIZE = 0x84
    GET_LBA_STATUS = 0x86


class LogPageID(IntEnum):
    """
    Common NVMe Log Page identifiers.

    Reference: NVMe Base Specification
    """

    SUPPORTED_LOG_PAGES = 0x00
    ERROR_INFORMATION = 0x01
    SMART_HEALTH = 0x02
    FIRMWARE_SLOT = 0x03
    CHANGED_NS_LIST = 0x04
    COMMANDS_SUPPORTED = 0x05
    DEVICE_SELF_TEST = 0x06
    TELEMETRY_HOST = 0x07
    TELEMETRY_CONTROLLER = 0x08
    ENDURANCE_GROUP = 0x09
    PREDICTABLE_LATENCY_PER_NVM_SET = 0x0A
    PREDICTABLE_LATENCY_EVENT_AGGREGATE = 0x0B
    ASYMMETRIC_NS_ACCESS = 0x0C
    PERSISTENT_EVENT = 0x0D
    LBA_STATUS_INFO = 0x0E
    ENDURANCE_GROUP_EVENT_AGGREGATE = 0x0F
    MEDIA_UNIT_STATUS = 0x10
    SUPPORTED_CAPACITY_CONFIG = 0x11
    FEATURE_ID_SUPPORTED_EFFECTS = 0x12
    NVME_MI_COMMANDS_SUPPORTED = 0x13
    COMMAND_SET_SPECIFIC_ID = 0x14  # NVMe 2.0+
    # Vendor specific: 0xC0-0xFF


class IdentifyCNS(IntEnum):
    """
    Identify Command CNS (Controller or Namespace Structure) values.

    Reference: NVMe Base Specification
    """

    NAMESPACE = 0x00
    CONTROLLER = 0x01
    ACTIVE_NS_LIST = 0x02
    NS_ID_DESCRIPTOR_LIST = 0x03
    NVM_SET_LIST = 0x04
    # Additional CNS values in NVMe 1.4+
    IO_COMMAND_SET_SPECIFIC_NS = 0x05
    IO_COMMAND_SET_SPECIFIC_CTRL = 0x06
    ACTIVE_NS_LIST_SPECIFIC = 0x07
    # NVMe 2.0+
    ALLOCATED_NS_LIST = 0x10
    ALLOCATED_NS = 0x11
    NS_CTRL_LIST = 0x12
    CTRL_LIST = 0x13
    PRIMARY_CTRL_CAPABILITIES = 0x14
    SECONDARY_CTRL_LIST = 0x15
    NS_GRANULARITY_LIST = 0x16
    UUID_LIST = 0x17
    DOMAIN_LIST = 0x18
    ENDURANCE_GROUP_LIST = 0x19
    ALLOCATED_NS_LIST_SPECIFIC = 0x1A
    ALLOCATED_NS_SPECIFIC = 0x1B


@dataclass
class CommandDWords:
    """
    NVMe Command DWords (CDW0-CDW15) for Admin commands.

    These are the command-specific dwords that follow the standard
    command header in an NVMe Admin command.
    """

    nsid: int = 0  # CDW1: Namespace ID
    cdw2: int = 0
    cdw3: int = 0
    cdw4: int = 0
    cdw5: int = 0
    cdw6: int = 0
    cdw7: int = 0
    cdw8: int = 0
    cdw9: int = 0
    cdw10: int = 0
    cdw11: int = 0
    cdw12: int = 0
    cdw13: int = 0
    cdw14: int = 0
    cdw15: int = 0

    def pack(self) -> bytes:
        """Pack CDW1-CDW15 into bytes (60 bytes total)."""
        return struct.pack(
            "<15I",
            self.nsid,
            self.cdw2,
            self.cdw3,
            self.cdw4,
            self.cdw5,
            self.cdw6,
            self.cdw7,
            self.cdw8,
            self.cdw9,
            self.cdw10,
            self.cdw11,
            self.cdw12,
            self.cdw13,
            self.cdw14,
            self.cdw15,
        )

    @classmethod
    def unpack(cls, data: bytes) -> CommandDWords:
        """Unpack CDW1-CDW15 from bytes."""
        if len(data) < 60:
            raise ValueError(f"Need 60 bytes for CDW1-15, got {len(data)}")
        values = struct.unpack("<15I", data[:60])
        return cls(
            nsid=values[0],
            cdw2=values[1],
            cdw3=values[2],
            cdw4=values[3],
            cdw5=values[4],
            cdw6=values[5],
            cdw7=values[6],
            cdw8=values[7],
            cdw9=values[8],
            cdw10=values[9],
            cdw11=values[10],
            cdw12=values[11],
            cdw13=values[12],
            cdw14=values[13],
            cdw15=values[14],
        )


@dataclass
class CommandCapsule:
    """
    NVMe-MI Command Capsule for Admin command tunneling.

    This is the NVMe-MI 2.0+ format for tunneling Admin commands.
    For NVMe-MI 1.2, use MISendRequest/MIReceiveRequest instead.

    Reference: NVMe-MI 2.0, Section 5.3

    Attributes:
        opcode: Admin command opcode
        command_id: Command identifier (for tracking)
        dwords: Command DWords (CDW1-CDW15)
        data: Optional data payload for the command
    """

    opcode: int
    command_id: int = 0
    dwords: CommandDWords = field(default_factory=CommandDWords)
    data: bytes = b""

    # NMIMT value for Admin Command (NVMe-MI 2.0)
    NMIMT_ADMIN_COMMAND = 0x04

    def pack(self) -> bytes:
        """
        Pack Command Capsule into bytes.

        Format (NVMe-MI 2.0):
            Byte 0:    NMIMT/ROR (0x04 for Admin Command Request)
            Byte 1:    Admin Opcode
            Bytes 2-3: Command ID
            Bytes 4-63: CDW1-CDW15 (60 bytes)
            Bytes 64+: Data (if any)

        Returns:
            Command Capsule bytes
        """
        header = struct.pack(
            "<BBH",
            self.NMIMT_ADMIN_COMMAND,  # NMIMT/ROR
            self.opcode,
            self.command_id,
        )
        return header + self.dwords.pack() + self.data

    @classmethod
    def identify_controller(cls, command_id: int = 0) -> CommandCapsule:
        """
        Create Identify Controller command capsule.

        Returns 4096 bytes of controller identification data including
        serial number, model number, firmware revision, etc.
        """
        dwords = CommandDWords(
            nsid=0,
            cdw10=IdentifyCNS.CONTROLLER,  # CNS = 1
        )
        return cls(
            opcode=AdminOpcode.IDENTIFY,
            command_id=command_id,
            dwords=dwords,
        )

    @classmethod
    def identify_namespace(cls, nsid: int = 1, command_id: int = 0) -> CommandCapsule:
        """
        Create Identify Namespace command capsule.

        Args:
            nsid: Namespace ID to identify
            command_id: Command identifier

        Returns 4096 bytes of namespace identification data.
        """
        dwords = CommandDWords(
            nsid=nsid,
            cdw10=IdentifyCNS.NAMESPACE,  # CNS = 0
        )
        return cls(
            opcode=AdminOpcode.IDENTIFY,
            command_id=command_id,
            dwords=dwords,
        )

    @classmethod
    def get_log_page(
        cls,
        log_id: int | LogPageID,
        numdl: int = 0x7F,
        offset: int = 0,
        nsid: int = 0xFFFFFFFF,
        command_id: int = 0,
    ) -> CommandCapsule:
        """
        Create Get Log Page command capsule.

        Args:
            log_id: Log Page Identifier
            numdl: Number of dwords to return minus 1 (default 128 dwords = 512 bytes)
            offset: Log page offset
            nsid: Namespace ID (0xFFFFFFFF for all namespaces)
            command_id: Command identifier
        """
        lid = log_id.value if isinstance(log_id, LogPageID) else log_id

        # CDW10: NUMDL (bits 27:16), LSP (bits 15:8), LID (bits 7:0)
        cdw10 = (numdl << 16) | lid

        # CDW12/13: Log Page Offset
        cdw12 = offset & 0xFFFFFFFF
        cdw13 = (offset >> 32) & 0xFFFFFFFF

        dwords = CommandDWords(
            nsid=nsid,
            cdw10=cdw10,
            cdw12=cdw12,
            cdw13=cdw13,
        )
        return cls(
            opcode=AdminOpcode.GET_LOG_PAGE,
            command_id=command_id,
            dwords=dwords,
        )

    @classmethod
    def get_smart_log(cls, nsid: int = 0xFFFFFFFF, command_id: int = 0) -> CommandCapsule:
        """
        Create Get SMART/Health Log command capsule.

        Returns 512 bytes of SMART health information.
        """
        return cls.get_log_page(
            log_id=LogPageID.SMART_HEALTH,
            numdl=0x7F,  # 128 dwords = 512 bytes
            nsid=nsid,
            command_id=command_id,
        )

    @classmethod
    def get_firmware_log(cls, command_id: int = 0) -> CommandCapsule:
        """
        Create Get Firmware Slot Information Log command capsule.

        Returns 512 bytes of firmware slot information.
        """
        return cls.get_log_page(
            log_id=LogPageID.FIRMWARE_SLOT,
            numdl=0x7F,  # 128 dwords = 512 bytes
            nsid=0,
            command_id=command_id,
        )

    @classmethod
    def get_error_log(cls, num_entries: int = 1, command_id: int = 0) -> CommandCapsule:
        """
        Create Get Error Log command capsule.

        Args:
            num_entries: Number of error log entries to retrieve (each 64 bytes)
            command_id: Command identifier

        Returns error log entries (64 bytes each).
        """
        # Each entry is 64 bytes = 16 dwords
        numdl = (num_entries * 16) - 1
        return cls.get_log_page(
            log_id=LogPageID.ERROR_INFORMATION,
            numdl=numdl,
            command_id=command_id,
        )

    @classmethod
    def get_features(
        cls,
        feature_id: int,
        nsid: int = 0,
        select: int = 0,
        command_id: int = 0,
    ) -> CommandCapsule:
        """
        Create Get Features command capsule.

        Args:
            feature_id: Feature Identifier
            nsid: Namespace ID (if applicable)
            select: Select field (0=current, 1=default, 2=saved, 3=supported)
            command_id: Command identifier
        """
        # CDW10: SEL (bits 10:8), FID (bits 7:0)
        cdw10 = (select << 8) | feature_id

        dwords = CommandDWords(
            nsid=nsid,
            cdw10=cdw10,
        )
        return cls(
            opcode=AdminOpcode.GET_FEATURES,
            command_id=command_id,
            dwords=dwords,
        )


@dataclass
class MISendRequest:
    """
    NVMe-MI 1.2 MI Send Request for Admin command tunneling.

    This is the older format used in NVMe-MI 1.2 for tunneling Admin commands.
    For NVMe-MI 2.0+, prefer CommandCapsule.

    Reference: NVMe-MI 1.2, Section 6.7
    """

    opcode: int
    dwords: CommandDWords = field(default_factory=CommandDWords)
    data: bytes = b""

    # MI Send opcode
    MI_SEND_OPCODE = 0x0D
    # NMIMT value for MI Command
    NMIMT_MI_COMMAND = 0x01

    def pack(self) -> bytes:
        """
        Pack MI Send request into bytes.

        Format (NVMe-MI 1.2):
            Byte 0:    NMIMT/ROR (0x01 for MI Command Request)
            Byte 1:    MI Opcode (0x0D for MI Send)
            Bytes 2-3: Reserved
            Byte 4:    Admin Opcode
            Bytes 5-7: Reserved
            Bytes 8-67: CDW1-CDW15 (60 bytes)
            Bytes 68+: Data (if any)

        Returns:
            MI Send request bytes
        """
        header = struct.pack(
            "<BBHBBBB",
            self.NMIMT_MI_COMMAND,  # NMIMT/ROR
            self.MI_SEND_OPCODE,  # MI Opcode
            0,  # Reserved
            self.opcode,  # Admin Opcode
            0,
            0,
            0,  # Reserved
        )
        return header + self.dwords.pack() + self.data


@dataclass
class MIReceiveRequest:
    """
    NVMe-MI 1.2 MI Receive Request for retrieving Admin command responses.

    Reference: NVMe-MI 1.2, Section 6.8
    """

    # MI Receive opcode
    MI_RECEIVE_OPCODE = 0x0E
    # NMIMT value for MI Command
    NMIMT_MI_COMMAND = 0x01

    def pack(self) -> bytes:
        """
        Pack MI Receive request into bytes.

        Format (NVMe-MI 1.2):
            Byte 0:    NMIMT/ROR (0x01 for MI Command Request)
            Byte 1:    MI Opcode (0x0E for MI Receive)
            Bytes 2-3: Reserved

        Returns:
            MI Receive request bytes
        """
        return struct.pack(
            "<BBH",
            self.NMIMT_MI_COMMAND,
            self.MI_RECEIVE_OPCODE,
            0,  # Reserved
        )


# Convenience functions for common operations


def build_identify_controller_1x() -> MISendRequest:
    """Build NVMe-MI 1.2 style Identify Controller request."""
    dwords = CommandDWords(
        nsid=0,
        cdw10=IdentifyCNS.CONTROLLER,
    )
    return MISendRequest(opcode=AdminOpcode.IDENTIFY, dwords=dwords)


def build_identify_controller_2x() -> CommandCapsule:
    """Build NVMe-MI 2.0+ style Identify Controller request."""
    return CommandCapsule.identify_controller()


def build_smart_log_1x() -> MISendRequest:
    """Build NVMe-MI 1.2 style SMART Log request."""
    dwords = CommandDWords(
        nsid=0xFFFFFFFF,
        cdw10=(0x7F << 16) | LogPageID.SMART_HEALTH,
    )
    return MISendRequest(opcode=AdminOpcode.GET_LOG_PAGE, dwords=dwords)


def build_smart_log_2x() -> CommandCapsule:
    """Build NVMe-MI 2.0+ style SMART Log request."""
    return CommandCapsule.get_smart_log()
