"""
NVMe-MI Management Interface command opcodes.
"""

from enum import IntEnum


class NVMeMIOpcode(IntEnum):
    """
    NVMe-MI Management Interface Command Opcodes per NVMe-MI Spec Figure 14.

    These opcodes identify the specific MI command being sent.
    Vendor-specific opcodes are in the range 0x80-0xFF (C0h-FFh per spec).
    """

    # Standard MI Commands (0x00-0x7F)
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
    # 0x0F-0x7F reserved

    # Vendor Specific (0xC0-0xFF)
    # These would be defined by specific vendors
    # VENDOR_EXAMPLE = 0xC0

    @classmethod
    def is_vendor_specific(cls, opcode: int) -> bool:
        """Check if an opcode is in the vendor-specific range."""
        return 0xC0 <= opcode <= 0xFF

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
