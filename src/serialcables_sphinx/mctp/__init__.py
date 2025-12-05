"""
MCTP (Management Component Transport Protocol) implementation.

Handles MCTP packet building and parsing per DMTF DSP0236 specification,
including SMBus/I2C physical layer framing.

Supports message fragmentation for payloads exceeding packet size limits:
- TX limit: 128 bytes per packet
- RX limit: 256 bytes per packet (MCU constraint)
"""

from serialcables_sphinx.mctp.builder import MCTPBuilder
from serialcables_sphinx.mctp.parser import MCTPParser
from serialcables_sphinx.mctp.header import MCTPHeader
from serialcables_sphinx.mctp.constants import (
    MCTPMessageType,
    MCTP_SMBUS_COMMAND_CODE,
    MCTP_HEADER_VERSION,
)
from serialcables_sphinx.mctp.fragmentation import (
    FragmentationConstants,
    FragmentationConfig,
    FragmentedMessage,
    MCTPFragment,
    MessageFragmenter,
    MessageReassembler,
    ReassemblyBuffer,
    PacketSequence,
)

__all__ = [
    # Core
    "MCTPBuilder",
    "MCTPParser",
    "MCTPHeader",
    "MCTPMessageType",
    "MCTP_SMBUS_COMMAND_CODE",
    "MCTP_HEADER_VERSION",
    # Fragmentation
    "FragmentationConstants",
    "FragmentationConfig",
    "FragmentedMessage",
    "MCTPFragment",
    "MessageFragmenter",
    "MessageReassembler",
    "ReassemblyBuffer",
    "PacketSequence",
]
