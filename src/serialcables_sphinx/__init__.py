"""
serialcables-sphinx - MCTP and NVMe-MI protocol library for Serial Cables hardware.

This library provides MCTP packet building, NVMe-MI command encoding,
and response decoding for use with HYDRA enclosures and NVMe devices.

Example:
    from serialcables_hydra import HYDRADevice
    from serialcables_sphinx import Sphinx

    hydra = HYDRADevice("/dev/ttyUSB0")
    sphinx = Sphinx(hydra)

    result = sphinx.nvme_mi.health_status_poll(eid=1)
    print(result.pretty_print())
"""

__version__ = "0.1.0"
__author__ = "Serial Cables, LLC"

# Main client
from serialcables_sphinx.sphinx import Sphinx

# MCTP components
from serialcables_sphinx.mctp.builder import MCTPBuilder
from serialcables_sphinx.mctp.parser import MCTPParser
from serialcables_sphinx.mctp.constants import (
    MCTPMessageType,
    MCTP_SMBUS_COMMAND_CODE,
)
from serialcables_sphinx.mctp.header import MCTPHeader

# NVMe-MI components
from serialcables_sphinx.nvme_mi.opcodes import NVMeMIOpcode
from serialcables_sphinx.nvme_mi.status import NVMeMIStatus
from serialcables_sphinx.nvme_mi.request import NVMeMIRequest
from serialcables_sphinx.nvme_mi.response import DecodedResponse, DecodedField
from serialcables_sphinx.nvme_mi.decoder import NVMeMIDecoder
from serialcables_sphinx.nvme_mi.registry import DecoderRegistry
from serialcables_sphinx.nvme_mi.base_decoder import ResponseDecoder
from serialcables_sphinx.nvme_mi.constants import (
    NVMeDataStructureType,
    ConfigurationIdentifier,
    CriticalWarningFlags,
)

# Transport interface
from serialcables_sphinx.transports.base import MCTPTransport

__all__ = [
    # Version
    "__version__",
    # Main client
    "Sphinx",
    # MCTP
    "MCTPBuilder",
    "MCTPParser",
    "MCTPHeader",
    "MCTPMessageType",
    "MCTP_SMBUS_COMMAND_CODE",
    # NVMe-MI
    "NVMeMIOpcode",
    "NVMeMIStatus",
    "NVMeMIRequest",
    "NVMeMIDecoder",
    "DecodedResponse",
    "DecodedField",
    "DecoderRegistry",
    "ResponseDecoder",
    "NVMeDataStructureType",
    "ConfigurationIdentifier",
    "CriticalWarningFlags",
    # Transport
    "MCTPTransport",
]
