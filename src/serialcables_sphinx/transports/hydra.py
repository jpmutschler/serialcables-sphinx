"""
HYDRA transport adapter for serialcables-hydra JBOFController.

Bridges the real serialcables-hydra JBOFController with the
MCTPTransport interface expected by Sphinx.

Example:
    from serialcables_hydra import JBOFController
    from serialcables_sphinx import Sphinx
    from serialcables_sphinx.transports.hydra import HYDRATransport
    
    # Connect to HYDRA
    jbof = JBOFController(port="/dev/ttyUSB0")
    
    # Wrap with transport adapter
    transport = HYDRATransport(jbof, slot=1)
    
    # Use with Sphinx
    sphinx = Sphinx(transport)
    result = sphinx.nvme_mi.health_status_poll(eid=1)
"""

from __future__ import annotations
from typing import Optional, List, TYPE_CHECKING
import time

from serialcables_sphinx.transports.base import (
    TransportError,
    TimeoutError,
    CommunicationError,
)

if TYPE_CHECKING:
    from serialcables_hydra import JBOFController


class HYDRATransport:
    """
    Transport adapter wrapping serialcables-hydra JBOFController.
    
    Provides MCTPTransport interface using JBOFController's I2C methods
    for MCTP-over-SMBus communication with NVMe devices.
    
    Attributes:
        jbof: The underlying JBOFController instance
        slot: Current target slot (1-8)
        default_address: Default SMBus address for NVMe-MI (0x3A)
        timeout: Response timeout in seconds
        verbose: Print packets if True
        
    Example:
        from serialcables_hydra import JBOFController
        from serialcables_sphinx.transports.hydra import HYDRATransport
        
        jbof = JBOFController(port="/dev/ttyUSB0")
        
        transport = HYDRATransport(jbof, slot=1)
        
        # Send raw MCTP packet
        response = transport.send_packet(packet_bytes)
    """
    
    def __init__(
        self,
        jbof: "JBOFController",
        slot: int = 1,
        default_address: int = 0x3A,
        timeout: float = 1.0,
        verbose: bool = False,
    ):
        """
        Initialize HYDRA transport adapter.
        
        Args:
            jbof: Connected JBOFController instance
            slot: Initial target slot (1-8)
            default_address: Default SMBus address (0x3A for NVMe-MI)
            timeout: Response timeout in seconds
            verbose: Print TX/RX packets
        """
        self._jbof = jbof
        self._slot = slot
        self._default_address = default_address
        self._timeout = timeout
        self._verbose = verbose
    
    @property
    def jbof(self) -> "JBOFController":
        """Get underlying JBOFController."""
        return self._jbof
    
    @property
    def slot(self) -> int:
        """Get current target slot."""
        return self._slot
    
    @slot.setter
    def slot(self, value: int) -> None:
        """Set target slot."""
        if not 1 <= value <= 8:
            raise ValueError(f"Slot must be 1-8, got {value}")
        self._slot = value
    
    def send_packet(self, packet: bytes) -> bytes:
        """
        Send MCTP packet and receive response.
        
        Extracts SMBus address from packet, sends via I2C write,
        then reads response from device.
        
        Args:
            packet: Complete MCTP-over-SMBus packet bytes
                    Format: [Addr][Cmd=0x0F][ByteCount][MCTP...][PEC]
            
        Returns:
            Response packet bytes
            
        Raises:
            TransportError: On communication failure
            TimeoutError: If response times out
        """
        if len(packet) < 4:
            raise TransportError(f"Packet too short: {len(packet)} bytes")
        
        # Extract address from packet (first byte)
        address = packet[0]
        
        # Data to write is everything after the address
        # The JBOFController.i2c_write handles the address separately
        write_data = list(packet[1:])
        
        if self._verbose:
            print(f"[HYDRATransport] TX slot={self._slot} addr=0x{address:02X}: {packet.hex(' ')}")
        
        # Send packet
        try:
            success = self._jbof.i2c_write(
                address=address,
                slot=self._slot,
                data=write_data,
            )
            if not success:
                raise CommunicationError("I2C write failed")
        except Exception as e:
            raise TransportError(f"Failed to send packet: {e}")
        
        # Wait briefly for device to process
        time.sleep(0.005)  # 5ms
        
        # Read response
        # For MCTP, we need to read from the response address (typically 0x20)
        # and get enough bytes for the response
        response_address = 0x20  # Host address for responses
        
        try:
            # Read response header first to get length
            # SMBus response: [Addr][Cmd][ByteCount][Data...][PEC]
            # We need to read at least 3 bytes to get byte count
            header = self._jbof.i2c_read(
                address=response_address,
                slot=self._slot,
                register=0x0F,  # MCTP command code as register
                length=3,
            )
            
            if not header or len(header) < 3:
                raise TimeoutError("No response from device")
            
            # Byte count at offset 2 tells us how much more to read
            byte_count = header[2]
            total_length = 3 + byte_count + 1  # header + data + PEC
            
            # Read full response
            response_data = self._jbof.i2c_read(
                address=response_address,
                slot=self._slot,
                register=0x0F,
                length=total_length,
            )
            
            if not response_data:
                raise TimeoutError("Failed to read response")
            
            response = bytes(response_data)
            
        except TimeoutError:
            raise
        except Exception as e:
            raise TransportError(f"Failed to read response: {e}")
        
        if self._verbose:
            print(f"[HYDRATransport] RX: {response.hex(' ')}")
        
        return response
    
    def set_target(
        self,
        slot: Optional[int] = None,
        address: Optional[int] = None,
    ) -> None:
        """
        Configure target slot and/or address.
        
        Args:
            slot: Target slot number (1-8)
            address: Target SMBus address
        """
        if slot is not None:
            self.slot = slot
        if address is not None:
            self._default_address = address
    
    # =========================================================================
    # Convenience methods exposing JBOFController functionality
    # =========================================================================
    
    def get_slot_info(self) -> dict:
        """Get information about current slot."""
        return self._jbof.show_slot_info(self._slot)
    
    def get_all_slots_info(self) -> List[dict]:
        """Get information about all slots."""
        return [self._jbof.show_slot_info(i) for i in range(1, 9)]
    
    def power_on_slot(self, slot: Optional[int] = None) -> bool:
        """Power on a slot."""
        target = slot or self._slot
        return self._jbof.slot_power(target, on=True)
    
    def power_off_slot(self, slot: Optional[int] = None) -> bool:
        """Power off a slot."""
        target = slot or self._slot
        return self._jbof.slot_power(target, on=False)
    
    def reset_slot(self, slot: Optional[int] = None) -> bool:
        """Reset SSD in slot."""
        target = slot or self._slot
        return self._jbof.ssd_reset(target)
    
    def smbus_reset(self) -> bool:
        """Reset SMBus interface."""
        return self._jbof.smbus_reset()


# Convenience factory function
def create_hydra_transport(
    port: str,
    slot: int = 1,
    **kwargs,
) -> HYDRATransport:
    """
    Create HYDRATransport with connected JBOFController.
    
    Convenience function that handles connection setup.
    
    Args:
        port: Serial port (e.g., "/dev/ttyUSB0", "COM3")
        slot: Initial target slot
        **kwargs: Additional arguments for HYDRATransport
        
    Returns:
        Connected HYDRATransport instance
        
    Example:
        transport = create_hydra_transport("/dev/ttyUSB0", slot=1)
        sphinx = Sphinx(transport)
    """
    from serialcables_hydra import JBOFController
    
    jbof = JBOFController(port=port)
    
    return HYDRATransport(jbof, slot=slot, **kwargs)
