"""
Transport layer implementations for Sphinx.

Defines the interface that HYDRA and other transports implement.
"""

from serialcables_sphinx.transports.base import (
    CommunicationError,
    MCTPTransport,
    PECError,
    TimeoutError,
    TransportError,
)
from serialcables_sphinx.transports.mock import (
    MockDeviceState,
    MockHYDRA,
    MockHYDRADevice,
    MockTransport,
)

# HYDRA adapter - only import if serialcables-hydra is available
try:
    from serialcables_sphinx.transports.hydra import (
        HYDRATransport,
        create_hydra_transport,
    )

    _HAVE_HYDRA = True
except ImportError:
    _HAVE_HYDRA = False
    HYDRATransport = None  # type: ignore[misc,assignment]
    create_hydra_transport = None  # type: ignore[assignment]

__all__ = [
    # Protocol
    "MCTPTransport",
    # Exceptions
    "TransportError",
    "TimeoutError",
    "CommunicationError",
    "PECError",
    # Mock
    "MockTransport",
    "MockDeviceState",
    "MockHYDRA",
    "MockHYDRADevice",
    # HYDRA (if available)
    "HYDRATransport",
    "create_hydra_transport",
]
