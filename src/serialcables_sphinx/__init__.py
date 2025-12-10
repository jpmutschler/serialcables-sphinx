"""
serialcables-sphinx - MCTP and NVMe-MI protocol library for Serial Cables hardware.

This library provides MCTP packet building, NVMe-MI command encoding,
and response decoding for use with HYDRA enclosures and NVMe devices.

Example:
    from serialcables_hydra import JBOFController
    from serialcables_sphinx import Sphinx
    from serialcables_sphinx.transports.hydra import HYDRATransport

    jbof = JBOFController(port="/dev/ttyUSB0")
    transport = HYDRATransport(jbof, slot=1)
    sphinx = Sphinx(transport)

    result = sphinx.nvme_mi.health_status_poll(eid=1)
    print(result.pretty_print())

    # Or use firmware shortcuts (HYDRA firmware v0.0.6+)
    from serialcables_sphinx.shortcuts import MCTPShortcuts
    shortcuts = MCTPShortcuts(jbof)
    health = shortcuts.get_health_status(slot=1)
    print(f"Temperature: {health.temperature_celsius}°C")
"""

__version__ = "0.1.0"
__author__ = "Serial Cables, LLC"

# Main client
# MCTP components
from serialcables_sphinx.mctp.builder import MCTPBuilder
from serialcables_sphinx.mctp.constants import (
    MCTP_SMBUS_COMMAND_CODE,
    MCTPMessageType,
)
from serialcables_sphinx.mctp.header import MCTPHeader
from serialcables_sphinx.mctp.parser import MCTPParser
from serialcables_sphinx.nvme_mi.base_decoder import ResponseDecoder
from serialcables_sphinx.nvme_mi.constants import (
    ConfigurationIdentifier,
    CriticalWarningFlags,
    NVMeDataStructureType,
)
from serialcables_sphinx.nvme_mi.decoder import NVMeMIDecoder

# NVMe-MI components
from serialcables_sphinx.nvme_mi.opcodes import NVMeMIOpcode
from serialcables_sphinx.nvme_mi.registry import DecoderRegistry
from serialcables_sphinx.nvme_mi.request import NVMeMIRequest
from serialcables_sphinx.nvme_mi.response import DecodedField, DecodedResponse
from serialcables_sphinx.nvme_mi.status import NVMeMIStatus

# Shortcuts (firmware convenience commands)
from serialcables_sphinx.shortcuts import (
    HealthStatusResult,
    MCTPShortcutCommand,
    MCTPShortcuts,
    SerialNumberResult,
    create_shortcuts,
)
from serialcables_sphinx.sphinx import Sphinx

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
    # Shortcuts
    "MCTPShortcuts",
    "SerialNumberResult",
    "HealthStatusResult",
    "MCTPShortcutCommand",
    "create_shortcuts",
]
