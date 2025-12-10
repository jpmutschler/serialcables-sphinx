"""
NVMe-MI Response Message status values.
"""

from enum import IntEnum


class NVMeMIStatus(IntEnum):
    """
    NVMe-MI Response Message Status Values per NVMe-MI Spec Figure 10.

    Status codes indicate the result of an MI command.
    Vendor-specific status codes are in the range 0xC0-0xFF.
    """

    # Success
    SUCCESS = 0x00

    # General status codes
    MORE_PROCESSING_REQUIRED = 0x01
    INTERNAL_ERROR = 0x02
    INVALID_PARAMETER = 0x03
    INVALID_COMMAND_SIZE = 0x04
    INVALID_INPUT_SIZE = 0x05
    ACCESS_DENIED = 0x06
    # 0x07 reserved
    VPD_UPDATES_EXCEEDED = 0x08
    VPD_ACCESS_DENIED = 0x09
    # 0x0A-0x1F reserved

    # MI-specific errors (0x20-0x3F)
    MI_GENERIC_ERROR = 0x20
    MESSAGE_FORMAT_ERROR = 0x21
    INVALID_OPCODE = 0x22
    INVALID_ENDPOINT = 0x23
    MCTP_ERROR = 0x24
    UNSPECIFIED_ERROR = 0x25
    # 0x26-0x3F reserved

    # 0x40-0xBF reserved

    # Vendor Specific (0xC0-0xFF)

    @classmethod
    def is_success(cls, status: int) -> bool:
        """Check if status indicates success."""
        return status == cls.SUCCESS

    @classmethod
    def is_vendor_specific(cls, status: int) -> bool:
        """Check if status is in vendor-specific range."""
        return 0xC0 <= status <= 0xFF

    @classmethod
    def decode(cls, value: int) -> str:
        """
        Return human-readable status string.

        Args:
            value: Status value

        Returns:
            Status name with hex value
        """
        try:
            status = cls(value)
            return f"{status.name} (0x{value:02X})"
        except ValueError:
            if cls.is_vendor_specific(value):
                return f"VENDOR_SPECIFIC (0x{value:02X})"
            return f"UNKNOWN_STATUS (0x{value:02X})"

    @classmethod
    def get_description(cls, value: int) -> str:
        """
        Return detailed description of status code.

        Args:
            value: Status value

        Returns:
            Human-readable description
        """
        descriptions = {
            cls.SUCCESS: "Command completed successfully",
            cls.MORE_PROCESSING_REQUIRED: "Command accepted, processing continues",
            cls.INTERNAL_ERROR: "Internal error in the Management Endpoint",
            cls.INVALID_PARAMETER: "One or more parameters are invalid",
            cls.INVALID_COMMAND_SIZE: "Command message size is invalid",
            cls.INVALID_INPUT_SIZE: "Input data size is invalid",
            cls.ACCESS_DENIED: "Access to the command is denied",
            cls.VPD_UPDATES_EXCEEDED: "VPD update limit has been exceeded",
            cls.VPD_ACCESS_DENIED: "Access to VPD is denied",
            cls.MI_GENERIC_ERROR: "Generic Management Interface error",
            cls.MESSAGE_FORMAT_ERROR: "Message format is invalid",
            cls.INVALID_OPCODE: "The opcode is not supported",
            cls.INVALID_ENDPOINT: "The specified endpoint is invalid",
            cls.MCTP_ERROR: "Error in MCTP transport",
            cls.UNSPECIFIED_ERROR: "Unspecified error occurred",
        }

        try:
            status = cls(value)
            return descriptions.get(status, f"Status code 0x{value:02X}")
        except ValueError:
            if cls.is_vendor_specific(value):
                return f"Vendor-specific status code 0x{value:02X}"
            return f"Reserved/unknown status code 0x{value:02X}"
