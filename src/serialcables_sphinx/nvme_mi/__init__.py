"""
NVMe Management Interface (NVMe-MI) implementation.

Provides encoding and decoding of NVMe-MI messages per the
NVM Express Management Interface Specification.
"""

from serialcables_sphinx.nvme_mi.opcodes import NVMeMIOpcode
from serialcables_sphinx.nvme_mi.status import NVMeMIStatus
from serialcables_sphinx.nvme_mi.constants import (
    NVMeMIMessageType,
    NVMeDataStructureType,
    ConfigurationIdentifier,
    CriticalWarningFlags,
)
from serialcables_sphinx.nvme_mi.request import NVMeMIRequest
from serialcables_sphinx.nvme_mi.response import DecodedResponse, DecodedField
from serialcables_sphinx.nvme_mi.decoder import NVMeMIDecoder
from serialcables_sphinx.nvme_mi.registry import DecoderRegistry
from serialcables_sphinx.nvme_mi.base_decoder import ResponseDecoder
from serialcables_sphinx.nvme_mi.client import NVMeMIClient

__all__ = [
    # Enums and constants
    "NVMeMIOpcode",
    "NVMeMIStatus",
    "NVMeMIMessageType",
    "NVMeDataStructureType",
    "ConfigurationIdentifier",
    "CriticalWarningFlags",
    # Request/Response
    "NVMeMIRequest",
    "DecodedResponse",
    "DecodedField",
    # Decoder
    "NVMeMIDecoder",
    "DecoderRegistry",
    "ResponseDecoder",
    # Client
    "NVMeMIClient",
]
