"""
NVMe Management Interface (NVMe-MI) implementation.

Provides encoding and decoding of NVMe-MI messages per the
NVM Express Management Interface Specification.

Supports both NVMe-MI 1.2 and NVMe-MI 2.x specifications.
"""

from serialcables_sphinx.nvme_mi.base_decoder import ResponseDecoder
from serialcables_sphinx.nvme_mi.capsule import (
    AdminOpcode,
    CommandCapsule,
    CommandDWords,
    IdentifyCNS,
    LogPageID,
    MIReceiveRequest,
    MISendRequest,
)
from serialcables_sphinx.nvme_mi.client import NVMeMIClient
from serialcables_sphinx.nvme_mi.constants import (
    BootPartitionID,
    ConfigurationIdentifier,
    CriticalWarningFlags,
    EnduranceGroupCriticalWarning,
    NVMeDataStructureType,
    NVMeMIMessageType,
    SecurityState,
)
from serialcables_sphinx.nvme_mi.decoder import NVMeMIDecoder
from serialcables_sphinx.nvme_mi.opcodes import NVMeMIOpcode
from serialcables_sphinx.nvme_mi.registry import DecoderRegistry
from serialcables_sphinx.nvme_mi.request import NVMeMIRequest
from serialcables_sphinx.nvme_mi.response import DecodedField, DecodedResponse
from serialcables_sphinx.nvme_mi.status import NVMeMIStatus
from serialcables_sphinx.nvme_mi.version import (
    DeviceCapabilities,
    NVMeMIVersion,
    check_opcode_compatibility,
    get_pcie_gen_estimate,
)

__all__ = [
    # Enums and constants
    "NVMeMIOpcode",
    "NVMeMIStatus",
    "NVMeMIMessageType",
    "NVMeDataStructureType",
    "ConfigurationIdentifier",
    "CriticalWarningFlags",
    # NVMe-MI 2.x constants
    "SecurityState",
    "BootPartitionID",
    "EnduranceGroupCriticalWarning",
    # Request/Response
    "NVMeMIRequest",
    "DecodedResponse",
    "DecodedField",
    # Command Capsule (Admin tunneling)
    "CommandCapsule",
    "CommandDWords",
    "MISendRequest",
    "MIReceiveRequest",
    "AdminOpcode",
    "LogPageID",
    "IdentifyCNS",
    # Decoder
    "NVMeMIDecoder",
    "DecoderRegistry",
    "ResponseDecoder",
    # Client
    "NVMeMIClient",
    # Version detection
    "NVMeMIVersion",
    "DeviceCapabilities",
    "check_opcode_compatibility",
    "get_pcie_gen_estimate",
]
