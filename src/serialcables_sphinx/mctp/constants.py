"""
MCTP constants and enumerations per DMTF DSP0236 and DSP0237.
"""

from enum import IntEnum

# MCTP over SMBus/I2C constants (DSP0237)
MCTP_SMBUS_COMMAND_CODE = 0x0F
MCTP_HEADER_VERSION = 0x01

# Default addressing
DEFAULT_SOURCE_EID = 0x00  # BMC/Host
DEFAULT_SMBUS_ADDRESS = 0x3A  # Common NVMe-MI address


class MCTPMessageType(IntEnum):
    """
    MCTP Message Types per DSP0236 Section 8.1.

    The message type field identifies the higher-layer protocol
    carried in the MCTP message payload.
    """

    MCTP_CONTROL = 0x00
    PLDM = 0x01
    NCSI = 0x02
    ETHERNET = 0x03
    NVME_MI = 0x04
    SPDM = 0x05
    SECUREDMSG = 0x06
    CXL_FM_API = 0x07
    CXL_CCI = 0x08
    # 0x09-0x3F reserved
    # 0x40-0x7E Vendor defined (PCI)
    VENDOR_DEFINED_PCI = 0x7E
    VENDOR_DEFINED_IANA = 0x7F
    # 0x80-0xFF reserved (high bit is integrity check flag)


class MCTPControlCommand(IntEnum):
    """
    MCTP Control Message command codes per DSP0236 Section 12.
    """

    SET_ENDPOINT_ID = 0x01
    GET_ENDPOINT_ID = 0x02
    GET_ENDPOINT_UUID = 0x03
    GET_MCTP_VERSION_SUPPORT = 0x04
    GET_MESSAGE_TYPE_SUPPORT = 0x05
    GET_VENDOR_DEFINED_MSG_SUPPORT = 0x06
    RESOLVE_ENDPOINT_ID = 0x07
    ALLOCATE_ENDPOINT_IDS = 0x08
    ROUTING_INFO_UPDATE = 0x09
    GET_ROUTING_TABLE_ENTRIES = 0x0A
    PREPARE_FOR_ENDPOINT_DISCOVERY = 0x0B
    ENDPOINT_DISCOVERY = 0x0C
    DISCOVERY_NOTIFY = 0x0D
    GET_NETWORK_ID = 0x0E
    QUERY_HOP = 0x0F
    RESOLVE_UUID = 0x10
    QUERY_RATE_LIMIT = 0x11
    REQUEST_TX_RATE_LIMIT = 0x12
    UPDATE_RATE_LIMIT = 0x13
    QUERY_SUPPORTED_INTERFACES = 0x14
