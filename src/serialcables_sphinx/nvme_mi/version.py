"""
NVMe-MI Version Detection and Compatibility.

Provides utilities for detecting device NVMe-MI version and selecting
appropriate protocol formats for communication.

Reference:
    - NVMe-MI 1.2, Section 6.1.1 (NVM Subsystem Information)
    - NVMe-MI 2.0, Section 6.1.1 (NVM Subsystem Information, extended)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from serialcables_sphinx.nvme_mi.response import DecodedResponse


class NVMeMIVersion(IntEnum):
    """
    NVMe-MI specification versions.

    Used for version comparison and feature detection.
    """

    UNKNOWN = 0
    V1_0 = 100  # 1.0
    V1_1 = 110  # 1.1
    V1_2 = 120  # 1.2
    V2_0 = 200  # 2.0
    V2_1 = 210  # 2.1

    @classmethod
    def from_version_numbers(cls, major: int, minor: int) -> NVMeMIVersion:
        """
        Convert major.minor version to enum value.

        Args:
            major: Major version number
            minor: Minor version number

        Returns:
            Closest matching NVMeMIVersion
        """
        version_num = major * 100 + minor * 10

        # Find closest match
        for v in sorted(cls, reverse=True):
            if v != cls.UNKNOWN and version_num >= v.value:
                return v

        return cls.UNKNOWN

    @property
    def major(self) -> int:
        """Get major version number."""
        if self == NVMeMIVersion.UNKNOWN:
            return 0
        return self.value // 100

    @property
    def minor(self) -> int:
        """Get minor version number."""
        if self == NVMeMIVersion.UNKNOWN:
            return 0
        return (self.value % 100) // 10

    def __str__(self) -> str:
        if self == NVMeMIVersion.UNKNOWN:
            return "Unknown"
        return f"{self.major}.{self.minor}"


@dataclass
class DeviceCapabilities:
    """
    Detected NVMe-MI device capabilities.

    This class stores the capabilities detected from a device,
    allowing the library to select appropriate protocol formats.
    """

    # Version information
    nvme_mi_version: NVMeMIVersion = NVMeMIVersion.UNKNOWN
    version_major: int = 0
    version_minor: int = 0

    # Supported commands (from Optional Commands Supported bitmap)
    supports_configuration_set: bool = False
    supports_configuration_get: bool = False
    supports_vpd_read: bool = False
    supports_vpd_write: bool = False
    supports_mi_reset: bool = False
    supports_ses_receive: bool = False
    supports_ses_send: bool = False
    supports_meb_read: bool = False
    supports_meb_write: bool = False
    supports_mi_send: bool = False
    supports_mi_receive: bool = False

    # NVMe-MI 2.0+ specific
    supports_security_commands: bool = False
    supports_boot_partition: bool = False

    # Device info
    num_ports: int = 0
    num_controllers: int = 0
    controller_ids: list[int] = field(default_factory=list)

    @property
    def supports_admin_tunneling(self) -> bool:
        """Check if device supports Admin command tunneling."""
        return self.supports_mi_send and self.supports_mi_receive

    @property
    def is_nvme_mi_2x(self) -> bool:
        """Check if device supports NVMe-MI 2.0 or later."""
        return self.nvme_mi_version >= NVMeMIVersion.V2_0

    @property
    def preferred_capsule_format(self) -> str:
        """
        Get preferred Admin command tunneling format.

        Returns:
            'capsule' for NVMe-MI 2.0+ Command Capsule format
            'mi_send' for NVMe-MI 1.x MI Send/Receive format
            'none' if Admin tunneling not supported
        """
        if not self.supports_admin_tunneling:
            return "none"
        if self.is_nvme_mi_2x:
            return "capsule"
        return "mi_send"

    @classmethod
    def from_subsystem_info(cls, response: DecodedResponse) -> DeviceCapabilities:
        """
        Create DeviceCapabilities from NVM Subsystem Information response.

        Args:
            response: Decoded response from Read Data Structure (type 0)

        Returns:
            DeviceCapabilities with detected features
        """
        caps = cls()

        if not response.success:
            return caps

        # Extract version
        major = response.get("NVMe-MI Major Version", 1)
        minor = response.get("NVMe-MI Minor Version", 0)

        if isinstance(major, int) and isinstance(minor, int):
            caps.version_major = major
            caps.version_minor = minor
            caps.nvme_mi_version = NVMeMIVersion.from_version_numbers(major, minor)

        # Extract port count
        num_ports = response.get("Number of Ports", 0)
        if isinstance(num_ports, int):
            caps.num_ports = num_ports

        # Parse Optional Commands Supported string
        ocs_str = response.get("Optional Commands Supported", "")
        if isinstance(ocs_str, str):
            ocs_lower = ocs_str.lower()
            caps.supports_configuration_set = "configuration set" in ocs_lower
            caps.supports_configuration_get = "configuration get" in ocs_lower
            caps.supports_vpd_read = "vpd read" in ocs_lower
            caps.supports_vpd_write = "vpd write" in ocs_lower
            caps.supports_mi_reset = "mi reset" in ocs_lower
            caps.supports_ses_receive = "ses receive" in ocs_lower
            caps.supports_ses_send = "ses send" in ocs_lower
            caps.supports_meb_read = "meb read" in ocs_lower
            caps.supports_meb_write = "meb write" in ocs_lower
            caps.supports_mi_send = "mi send" in ocs_lower
            caps.supports_mi_receive = "mi receive" in ocs_lower

        # NVMe-MI 2.0+ features
        if caps.is_nvme_mi_2x:
            caps.supports_security_commands = True
            caps.supports_boot_partition = True

        return caps

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "nvme_mi_version": str(self.nvme_mi_version),
            "version_major": self.version_major,
            "version_minor": self.version_minor,
            "supports_admin_tunneling": self.supports_admin_tunneling,
            "preferred_capsule_format": self.preferred_capsule_format,
            "is_nvme_mi_2x": self.is_nvme_mi_2x,
            "num_ports": self.num_ports,
            "num_controllers": self.num_controllers,
            "controller_ids": self.controller_ids,
            "supported_commands": {
                "configuration_set": self.supports_configuration_set,
                "configuration_get": self.supports_configuration_get,
                "vpd_read": self.supports_vpd_read,
                "vpd_write": self.supports_vpd_write,
                "mi_reset": self.supports_mi_reset,
                "ses_receive": self.supports_ses_receive,
                "ses_send": self.supports_ses_send,
                "meb_read": self.supports_meb_read,
                "meb_write": self.supports_meb_write,
                "mi_send": self.supports_mi_send,
                "mi_receive": self.supports_mi_receive,
                "security": self.supports_security_commands,
                "boot_partition": self.supports_boot_partition,
            },
        }


def check_opcode_compatibility(opcode: int, capabilities: DeviceCapabilities) -> tuple[bool, str]:
    """
    Check if an opcode is compatible with device capabilities.

    Args:
        opcode: NVMe-MI opcode to check
        capabilities: Detected device capabilities

    Returns:
        Tuple of (is_compatible, reason)
    """
    from serialcables_sphinx.nvme_mi.opcodes import NVMeMIOpcode

    # Check version requirement
    min_version = NVMeMIOpcode.get_min_version(opcode)
    device_version = (capabilities.version_major, capabilities.version_minor)

    if device_version < min_version:
        return (
            False,
            f"Opcode requires NVMe-MI {min_version[0]}.{min_version[1]}, "
            f"device supports {capabilities.nvme_mi_version}",
        )

    # Check specific command support
    opcode_support_map = {
        NVMeMIOpcode.CONFIGURATION_SET: capabilities.supports_configuration_set,
        NVMeMIOpcode.CONFIGURATION_GET: capabilities.supports_configuration_get,
        NVMeMIOpcode.VPD_READ: capabilities.supports_vpd_read,
        NVMeMIOpcode.VPD_WRITE: capabilities.supports_vpd_write,
        NVMeMIOpcode.MI_RESET: capabilities.supports_mi_reset,
        NVMeMIOpcode.SES_RECEIVE: capabilities.supports_ses_receive,
        NVMeMIOpcode.SES_SEND: capabilities.supports_ses_send,
        NVMeMIOpcode.MANAGEMENT_ENDPOINT_BUFFER_READ: capabilities.supports_meb_read,
        NVMeMIOpcode.MANAGEMENT_ENDPOINT_BUFFER_WRITE: capabilities.supports_meb_write,
        NVMeMIOpcode.MI_SEND: capabilities.supports_mi_send,
        NVMeMIOpcode.MI_RECEIVE: capabilities.supports_mi_receive,
    }

    try:
        opcode_enum = NVMeMIOpcode(opcode)
        if opcode_enum in opcode_support_map:
            if not opcode_support_map[opcode_enum]:
                return (False, f"Device does not support {opcode_enum.name}")
    except ValueError:
        pass  # Unknown opcode, allow it

    return (True, "Compatible")


def get_pcie_gen_estimate(capabilities: DeviceCapabilities) -> str:
    """
    Estimate PCIe generation based on NVMe-MI version.

    This is a rough estimate - actual PCIe gen depends on the device.

    Args:
        capabilities: Device capabilities

    Returns:
        Estimated PCIe generation string
    """
    version = capabilities.nvme_mi_version

    if version >= NVMeMIVersion.V2_0:
        return "Gen6+ (estimated)"
    elif version >= NVMeMIVersion.V1_2:
        return "Gen4/Gen5 (estimated)"
    elif version >= NVMeMIVersion.V1_1:
        return "Gen3/Gen4 (estimated)"
    elif version >= NVMeMIVersion.V1_0:
        return "Gen3 (estimated)"
    else:
        return "Unknown"
