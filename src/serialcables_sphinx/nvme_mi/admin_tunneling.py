"""
NVMe-MI Admin Command Tunneling via MI Send/Receive.

MI Send (0x0D) and MI Receive (0x0E) allow tunneling NVMe Admin commands
through the NVMe-MI interface. This is essential for:
- Compliance testing (UNH-IOL requires full admin command coverage)
- Accessing Identify data, Log Pages, Features through management interface
- Complete device characterization without PCIe access

Reference: NVMe-MI 1.2 Specification, Section 6.4 (MI Send/Receive)

Admin commands that can be tunneled:
- Identify (06h) - Controller, Namespace, etc.
- Get Log Page (02h) - SMART, Error Log, Firmware Slot, etc.
- Get Features (0Ah) - Arbitration, Power Management, Temperature, etc.
- Set Features (09h) - Configuration changes
- Firmware operations (10h-13h) - Download, Commit, etc.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class AdminOpcode(IntEnum):
    """
    NVMe Admin Command Opcodes that can be tunneled via MI Send/Receive.

    Reference: NVMe Base Specification
    """

    # Identify operations
    DELETE_IO_SQ = 0x00
    CREATE_IO_SQ = 0x01
    GET_LOG_PAGE = 0x02
    DELETE_IO_CQ = 0x04
    CREATE_IO_CQ = 0x05
    IDENTIFY = 0x06
    ABORT = 0x08
    SET_FEATURES = 0x09
    GET_FEATURES = 0x0A
    ASYNC_EVENT_REQ = 0x0C
    NS_MANAGEMENT = 0x0D
    FIRMWARE_COMMIT = 0x10
    FIRMWARE_DOWNLOAD = 0x11
    DEVICE_SELF_TEST = 0x14
    NS_ATTACHMENT = 0x15
    KEEP_ALIVE = 0x18
    DIRECTIVE_SEND = 0x19
    DIRECTIVE_RECEIVE = 0x1A
    VIRTUALIZATION_MGMT = 0x1C
    NVME_MI_SEND = 0x1D
    NVME_MI_RECEIVE = 0x1E
    CAPACITY_MGMT = 0x20
    LOCKDOWN = 0x24
    DOORBELL_BUFFER_CONFIG = 0x7C
    FABRICS_COMMAND = 0x7F
    FORMAT_NVM = 0x80
    SECURITY_SEND = 0x81
    SECURITY_RECEIVE = 0x82
    SANITIZE = 0x84
    GET_LBA_STATUS = 0x86


class IdentifyCNS(IntEnum):
    """
    Identify CNS (Controller or Namespace Structure) values.
    """

    NAMESPACE = 0x00  # Identify Namespace
    CONTROLLER = 0x01  # Identify Controller
    ACTIVE_NS_LIST = 0x02  # Active Namespace ID List
    NS_ID_DESC_LIST = 0x03  # Namespace Identification Descriptor List
    NVM_SET_LIST = 0x04  # NVM Set List
    IO_CMD_SET_NS = 0x05  # I/O Command Set specific Namespace
    IO_CMD_SET_CTRL = 0x06  # I/O Command Set specific Controller
    IO_CMD_SET_ACTIVE_NS = 0x07  # I/O Command Set specific Active NS List
    ALLOCATED_NS_LIST = 0x10  # Allocated Namespace ID List
    ALLOCATED_NS = 0x11  # Identify Namespace for Allocated NSID
    ATTACHED_CTRL_LIST = 0x12  # Controller List Attached to NSID
    CTRL_LIST = 0x13  # Controller List
    PRIMARY_CTRL_CAPS = 0x14  # Primary Controller Capabilities
    SECONDARY_CTRL_LIST = 0x15  # Secondary Controller List
    NS_GRANULARITY_LIST = 0x16  # Namespace Granularity List
    UUID_LIST = 0x17  # UUID List
    DOMAIN_LIST = 0x18  # Domain List
    ENDURANCE_GROUP_LIST = 0x19  # Endurance Group List
    ALLOCATED_NS_LIST_IO = 0x1A  # Allocated NS List for IO Command Set
    ALLOCATED_NS_IO = 0x1B  # Identify Allocated NS for IO Command Set
    IO_CMD_SET = 0x1C  # I/O Command Set data structure


class LogPageIdentifier(IntEnum):
    """
    Log Page Identifiers for Get Log Page command.
    """

    # Mandatory Log Pages
    SUPPORTED_LOG_PAGES = 0x00
    ERROR_INFO = 0x01
    SMART_HEALTH = 0x02
    FIRMWARE_SLOT = 0x03
    CHANGED_NS_LIST = 0x04
    COMMANDS_SUPPORTED = 0x05
    DEVICE_SELF_TEST = 0x06
    TELEMETRY_HOST = 0x07
    TELEMETRY_CTRL = 0x08
    ENDURANCE_GROUP_INFO = 0x09
    PREDICTABLE_LATENCY_PER_NVM_SET = 0x0A
    PREDICTABLE_LATENCY_EVENT_AGG = 0x0B
    ASYMMETRIC_NS_ACCESS = 0x0C
    PERSISTENT_EVENT_LOG = 0x0D
    LBA_STATUS_INFO = 0x0E
    ENDURANCE_GROUP_EVENT_AGG = 0x0F
    MEDIA_UNIT_STATUS = 0x10
    SUPPORTED_CAPACITY_CFG = 0x11
    FEATURE_ID_SUPPORTED = 0x12
    NVME_MI_COMMANDS_SUPPORTED = 0x13
    COMMAND_AND_FEATURE_LOCKDOWN = 0x14
    BOOT_PARTITION = 0x15
    ROTATIONAL_MEDIA_INFO = 0x16
    # 0x17-0x6F Reserved
    DISCOVERY = 0x70  # NVMe-oF
    # 0x71-0x7F Reserved for NVMe-oF
    RESERVATION_NOTIFICATION = 0x80
    SANITIZE_STATUS = 0x81
    # 0x82-0xBF Reserved
    # 0xC0-0xFF Vendor Specific


class FeatureIdentifier(IntEnum):
    """
    Feature Identifiers for Get/Set Features commands.
    """

    ARBITRATION = 0x01
    POWER_MANAGEMENT = 0x02
    LBA_RANGE_TYPE = 0x03
    TEMPERATURE_THRESHOLD = 0x04
    ERROR_RECOVERY = 0x05
    VOLATILE_WRITE_CACHE = 0x06
    NUMBER_OF_QUEUES = 0x07
    INTERRUPT_COALESCING = 0x08
    INTERRUPT_VECTOR_CONFIG = 0x09
    WRITE_ATOMICITY_NORMAL = 0x0A
    ASYNC_EVENT_CONFIG = 0x0B
    AUTO_POWER_STATE_TRANSITION = 0x0C
    HOST_MEMORY_BUFFER = 0x0D
    TIMESTAMP = 0x0E
    KEEP_ALIVE_TIMER = 0x0F
    HOST_CTRL_THERMAL_MGMT = 0x10
    NON_OP_POWER_STATE_CONFIG = 0x11
    READ_RECOVERY_LEVEL_CONFIG = 0x12
    PREDICTABLE_LATENCY_MODE_CONFIG = 0x13
    PREDICTABLE_LATENCY_MODE_WINDOW = 0x14
    LBA_STATUS_INFO_REPORT_INTERVAL = 0x15
    HOST_BEHAVIOR_SUPPORT = 0x16
    SANITIZE_CONFIG = 0x17
    ENDURANCE_GROUP_EVENT_CONFIG = 0x18
    IO_CMD_SET_PROFILE = 0x19
    SPINUP_CONTROL = 0x1A
    ENHANCED_CONTROLLER_METADATA = 0x7D
    CONTROLLER_METADATA = 0x7E
    NAMESPACE_METADATA = 0x7F
    SOFTWARE_PROGRESS_MARKER = 0x80
    HOST_IDENTIFIER = 0x81
    RESERVATION_NOTIFICATION_MASK = 0x82
    RESERVATION_PERSISTENCE = 0x83
    NAMESPACE_WRITE_PROTECT_CONFIG = 0x84
    # 0x85-0xBF Reserved
    # 0xC0-0xFF Vendor Specific


@dataclass
class MISendRequest:
    """
    MI Send Request structure.

    Format (NVMe-MI 1.2, Figure 42):
    Byte 0: Opcode (0x0D)
    Bytes 1-3: Reserved
    Bytes 4-7: DWORD 0 (Controller ID, etc.)
    Bytes 8-11: DWORD 1 (Admin Opcode, etc.)
    Bytes 12+: Command-specific data
    """

    admin_opcode: int
    controller_id: int = 0
    nsid: int = 0
    cdw10: int = 0
    cdw11: int = 0
    cdw12: int = 0
    cdw13: int = 0
    cdw14: int = 0
    cdw15: int = 0
    data: bytes = b""

    def pack(self) -> bytes:
        """Pack MI Send request payload."""
        # DWORD 0: Controller ID (bits 15:0), Reserved
        dword0 = self.controller_id & 0xFFFF

        # DWORD 1: Admin Opcode (bits 7:0), Reserved
        dword1 = self.admin_opcode & 0xFF

        # Command DWORDs
        payload = struct.pack(
            "<IIIIIIIII",
            dword0,
            dword1,
            self.nsid,
            self.cdw10,
            self.cdw11,
            self.cdw12,
            self.cdw13,
            self.cdw14,
            self.cdw15,
        )

        return payload + self.data

    @classmethod
    def identify_controller(cls, controller_id: int = 0) -> MISendRequest:
        """Create Identify Controller request."""
        return cls(
            admin_opcode=AdminOpcode.IDENTIFY,
            controller_id=controller_id,
            cdw10=IdentifyCNS.CONTROLLER,
        )

    @classmethod
    def identify_namespace(cls, nsid: int, controller_id: int = 0) -> MISendRequest:
        """Create Identify Namespace request."""
        return cls(
            admin_opcode=AdminOpcode.IDENTIFY,
            controller_id=controller_id,
            nsid=nsid,
            cdw10=IdentifyCNS.NAMESPACE,
        )

    @classmethod
    def get_log_page(
        cls,
        log_id: int,
        length: int = 512,
        offset: int = 0,
        controller_id: int = 0,
        nsid: int = 0xFFFFFFFF,  # Global
    ) -> MISendRequest:
        """Create Get Log Page request."""
        # CDW10: Log Page ID, LSP, RAE, NUMDL
        numdl = (length // 4) - 1  # Number of DWORDs - 1 (lower 16 bits)
        cdw10 = (log_id & 0xFF) | ((numdl & 0xFFFF) << 16)

        # CDW11: NUMDU (upper 16 bits of NUMD), Log Specific Identifier
        numdu = (numdl >> 16) & 0xFFFF
        cdw11 = numdu

        # CDW12-13: Log Page Offset (bytes)
        cdw12 = offset & 0xFFFFFFFF
        cdw13 = (offset >> 32) & 0xFFFFFFFF

        return cls(
            admin_opcode=AdminOpcode.GET_LOG_PAGE,
            controller_id=controller_id,
            nsid=nsid,
            cdw10=cdw10,
            cdw11=cdw11,
            cdw12=cdw12,
            cdw13=cdw13,
        )

    @classmethod
    def get_smart_log(cls, controller_id: int = 0) -> MISendRequest:
        """Create Get SMART/Health Log Page request."""
        return cls.get_log_page(
            log_id=LogPageIdentifier.SMART_HEALTH,
            length=512,
            controller_id=controller_id,
        )

    @classmethod
    def get_firmware_slot_log(cls, controller_id: int = 0) -> MISendRequest:
        """Create Get Firmware Slot Info Log Page request."""
        return cls.get_log_page(
            log_id=LogPageIdentifier.FIRMWARE_SLOT,
            length=512,
            controller_id=controller_id,
        )

    @classmethod
    def get_error_log(cls, controller_id: int = 0, num_entries: int = 1) -> MISendRequest:
        """Create Get Error Information Log Page request."""
        # Each error entry is 64 bytes
        return cls.get_log_page(
            log_id=LogPageIdentifier.ERROR_INFO,
            length=64 * num_entries,
            controller_id=controller_id,
        )

    @classmethod
    def get_features(
        cls,
        feature_id: int,
        controller_id: int = 0,
        nsid: int = 0,
        select: int = 0,  # 0=Current, 1=Default, 2=Saved, 3=Supported Capabilities
    ) -> MISendRequest:
        """Create Get Features request."""
        # CDW10: FID (7:0), SEL (10:8)
        cdw10 = (feature_id & 0xFF) | ((select & 0x7) << 8)

        return cls(
            admin_opcode=AdminOpcode.GET_FEATURES,
            controller_id=controller_id,
            nsid=nsid,
            cdw10=cdw10,
        )


@dataclass
class MIReceiveRequest:
    """
    MI Receive Request structure.

    Used to retrieve response data from a previous MI Send command.

    Format (NVMe-MI 1.2, Figure 44):
    Byte 0: Opcode (0x0E)
    Bytes 1-3: Reserved
    Bytes 4-7: DWORD 0 (Controller ID)
    Bytes 8-11: DWORD 1 (Response DWORD 0 from MI Send)
    """

    controller_id: int = 0
    response_dword0: int = 0  # From MI Send response

    def pack(self) -> bytes:
        """Pack MI Receive request payload."""
        return struct.pack(
            "<II",
            self.controller_id & 0xFFFF,
            self.response_dword0,
        )


@dataclass
class AdminTunneledResponse:
    """
    Response from an admin command tunneled via MI Send/Receive.
    """

    # MI-level status
    mi_success: bool
    mi_status: int
    mi_status_name: str

    # Admin command status (from completion queue entry)
    admin_success: bool
    admin_status: int  # Status Code (SC)
    admin_status_type: int  # Status Code Type (SCT)

    # Response data
    data: bytes = b""
    dword0: int = 0  # CDW0 from completion

    # Timing
    latency_ms: float = 0.0

    # Error info
    error: str | None = None

    @property
    def success(self) -> bool:
        """Overall success (both MI and Admin)."""
        return self.mi_success and self.admin_success

    def get_identify_data(self) -> dict[str, Any] | None:
        """Parse Identify Controller/Namespace data."""
        if not self.success or len(self.data) < 256:
            return None

        # This is a simplified parser - full implementation would decode
        # all fields per NVMe spec
        result = {}

        # Common Identify Controller fields (first 256 bytes)
        result["vid"] = struct.unpack_from("<H", self.data, 0)[0]
        result["ssvid"] = struct.unpack_from("<H", self.data, 2)[0]
        result["sn"] = self.data[4:24].decode("ascii", errors="ignore").strip()
        result["mn"] = self.data[24:64].decode("ascii", errors="ignore").strip()
        result["fr"] = self.data[64:72].decode("ascii", errors="ignore").strip()
        result["rab"] = self.data[72]
        result["ieee"] = self.data[73:76].hex()

        return result

    def get_smart_data(self) -> dict[str, Any] | None:
        """Parse SMART/Health Log data."""
        if not self.success or len(self.data) < 512:
            return None

        result = {}

        result["critical_warning"] = self.data[0]
        result["composite_temperature"] = struct.unpack_from("<H", self.data, 1)[0]
        result["available_spare"] = self.data[3]
        result["available_spare_threshold"] = self.data[4]
        result["percentage_used"] = self.data[5]
        result["endurance_group_critical_warning"] = self.data[6]

        # Data units read/written (128-bit values)
        result["data_units_read"] = int.from_bytes(self.data[32:48], "little")
        result["data_units_written"] = int.from_bytes(self.data[48:64], "little")
        result["host_reads"] = int.from_bytes(self.data[64:80], "little")
        result["host_writes"] = int.from_bytes(self.data[80:96], "little")
        result["controller_busy_time"] = int.from_bytes(self.data[96:112], "little")
        result["power_cycles"] = int.from_bytes(self.data[112:128], "little")
        result["power_on_hours"] = int.from_bytes(self.data[128:144], "little")
        result["unsafe_shutdowns"] = int.from_bytes(self.data[144:160], "little")
        result["media_errors"] = int.from_bytes(self.data[160:176], "little")
        result["error_log_entries"] = int.from_bytes(self.data[176:192], "little")

        return result


# Configuration identifiers that need expansion
class ExtendedConfigurationIdentifier(IntEnum):
    """
    Extended Configuration Identifiers per NVMe-MI 1.2.

    Includes all standard identifiers plus vendor-specific range.
    """

    # Standard identifiers
    SMBUS_I2C_FREQUENCY = 0x01
    HEALTH_STATUS_CHANGE = 0x02
    MCTP_TRANSMISSION_UNIT = 0x03

    # Additional identifiers (check device support)
    SMBUS_I2C_ADDRESS = 0x04
    VPD_WRITE_ENABLED = 0x05
    MEB_ENABLED = 0x06

    # Vendor specific range: 0x80-0xFF
    VENDOR_SPECIFIC_START = 0x80

    @classmethod
    def is_vendor_specific(cls, config_id: int) -> bool:
        """Check if configuration ID is vendor-specific."""
        return config_id >= 0x80


@dataclass
class ConfigurationValue:
    """
    Configuration value with metadata.
    """

    config_id: int
    config_name: str
    value: int
    raw_data: bytes
    port_id: int = 0
    success: bool = True
    error: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "config_id": f"0x{self.config_id:02X}",
            "config_name": self.config_name,
            "value": self.value,
            "raw_hex": self.raw_data.hex(),
            "port_id": self.port_id,
            "success": self.success,
            "error": self.error,
        }
