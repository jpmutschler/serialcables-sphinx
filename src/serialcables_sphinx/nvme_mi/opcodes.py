"""
NVMe-MI Management Interface command opcodes.

Supports NVMe-MI 1.2 and 2.x specifications.
"""

from enum import IntEnum


class NVMeMIOpcode(IntEnum):
    """
    NVMe-MI Management Interface Command Opcodes.

    Reference:
        - NVMe-MI 1.2, Figure 14
        - NVMe-MI 2.0/2.1, Figure 14 (extended)

    These opcodes identify the specific MI command being sent.
    Vendor-specific opcodes are in the range 0xC0-0xFF.
    """

    # ==========================================================================
    # Standard MI Commands (NVMe-MI 1.2)
    # ==========================================================================
    READ_NVME_MI_DATA_STRUCTURE = 0x00
    NVM_SUBSYSTEM_HEALTH_STATUS_POLL = 0x01
    CONTROLLER_HEALTH_STATUS_POLL = 0x02
    CONFIGURATION_SET = 0x03
    CONFIGURATION_GET = 0x04
    VPD_READ = 0x05
    VPD_WRITE = 0x06
    MI_RESET = 0x07
    SES_RECEIVE = 0x08
    SES_SEND = 0x09
    MANAGEMENT_ENDPOINT_BUFFER_READ = 0x0A
    MANAGEMENT_ENDPOINT_BUFFER_WRITE = 0x0B
    # 0x0C reserved
    MI_SEND = 0x0D
    MI_RECEIVE = 0x0E
    # 0x0F reserved

    # ==========================================================================
    # NVMe-MI 2.0+ Commands (PCIe Gen6+)
    # ==========================================================================
    GET_BOOT_PARTITION_CONFIGURATION = 0x10
    SET_BOOT_PARTITION_CONFIGURATION = 0x11
    GET_SECURITY_STATE = 0x12
    SET_SECURITY_STATE = 0x13
    SECURITY_SEND = 0x14
    SECURITY_RECEIVE = 0x15
    # 0x16-0x1F reserved for future security commands

    # ==========================================================================
    # NVMe-MI 2.1+ Commands
    # ==========================================================================
    GET_FEATURES = 0x20  # MI Get Features (distinct from Admin Get Features)
    SET_FEATURES = 0x21  # MI Set Features (distinct from Admin Set Features)
    # 0x22-0x7F reserved

    # Vendor Specific (0xC0-0xFF)
    # These would be defined by specific vendors
    # VENDOR_EXAMPLE = 0xC0

    @classmethod
    def is_vendor_specific(cls, opcode: int) -> bool:
        """Check if an opcode is in the vendor-specific range."""
        return 0xC0 <= opcode <= 0xFF

    @classmethod
    def is_nvme_mi_2x_command(cls, opcode: int) -> bool:
        """Check if an opcode requires NVMe-MI 2.0 or later."""
        return opcode >= 0x10 and opcode <= 0x7F

    @classmethod
    def decode(cls, value: int) -> str:
        """
        Return human-readable opcode string.

        Args:
            value: Opcode value

        Returns:
            Opcode name or description
        """
        try:
            return cls(value).name
        except ValueError:
            if cls.is_vendor_specific(value):
                return f"VENDOR_SPECIFIC_0x{value:02X}"
            return f"RESERVED_0x{value:02X}"

    @classmethod
    def get_min_version(cls, opcode: int) -> tuple[int, int]:
        """
        Get minimum NVMe-MI version required for an opcode.

        Args:
            opcode: MI opcode value

        Returns:
            Tuple of (major, minor) version
        """
        if opcode <= 0x0E:
            return (1, 0)  # NVMe-MI 1.0+
        elif opcode <= 0x15:
            return (2, 0)  # NVMe-MI 2.0+
        elif opcode <= 0x21:
            return (2, 1)  # NVMe-MI 2.1+
        else:
            return (2, 1)  # Assume latest for unknown
