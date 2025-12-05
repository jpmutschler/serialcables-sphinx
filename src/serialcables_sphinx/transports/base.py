"""
Transport interface definition.

Defines the protocol that HYDRA and other transports must implement.
"""

from __future__ import annotations
from typing import Protocol, Optional, runtime_checkable


@runtime_checkable
class MCTPTransport(Protocol):
    """
    Protocol (interface) that any MCTP transport must implement.
    
    HYDRA implements this interface, but so could other transports
    like direct I2C adapters or test fixtures.
    
    Example implementation:
        class HYDRADevice(MCTPTransport):
            def send_packet(self, packet: bytes) -> bytes:
                # Send via serial, return response
                ...
            
            def set_target(self, slot: int = None, address: int = None) -> None:
                # Configure mux routing
                ...
    """
    
    def send_packet(self, packet: bytes) -> bytes:
        """
        Send raw packet bytes and return raw response bytes.
        
        The packet should be a complete MCTP-over-SMBus frame,
        ready to be transmitted on the wire.
        
        Args:
            packet: Complete packet bytes (MCTP-framed)
            
        Returns:
            Raw response bytes from device
            
        Raises:
            TransportError: If communication fails
        """
        ...
    
    def set_target(
        self,
        slot: Optional[int] = None,
        address: Optional[int] = None,
    ) -> None:
        """
        Configure target routing (optional, transport-specific).
        
        For HYDRA, this would select the mux channel.
        Other transports may ignore this or use it differently.
        
        Args:
            slot: Physical slot number (if applicable)
            address: Bus address (if applicable)
        """
        ...


class TransportError(Exception):
    """Base exception for transport errors."""
    pass


class TimeoutError(TransportError):
    """Timeout waiting for response."""
    pass


class CommunicationError(TransportError):
    """Error in communication with device."""
    pass


class PECError(TransportError):
    """Packet Error Code validation failed."""
    pass
