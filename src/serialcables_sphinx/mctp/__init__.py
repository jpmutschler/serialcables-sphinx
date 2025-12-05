"""
MCTP (Management Component Transport Protocol) implementation.

Handles MCTP packet building and parsing per DMTF DSP0236 specification,
including SMBus/I2C physical layer framing.
"""

from serialcables_sphinx.mctp.builder import MCTPBuilder
from serialcables_sphinx.mctp.parser import MCTPParser
from serialcables_sphinx.mctp.header import MCTPHeader
from serialcables_sphinx.mctp.constants import (
    MCTPMessageType,
    MCTP_SMBUS_COMMAND_CODE,
    MCTP_HEADER_VERSION,
)

__all__ = [
    "MCTPBuilder",
    "MCTPParser",
    "MCTPHeader",
    "MCTPMessageType",
    "MCTP_SMBUS_COMMAND_CODE",
    "MCTP_HEADER_VERSION",
]
