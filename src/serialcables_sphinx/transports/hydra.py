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

from dataclasses import dataclass
from typing import TYPE_CHECKING

from serialcables_sphinx.transports.base import (
    CommunicationError,
    TimeoutError,
    TransportError,
)

if TYPE_CHECKING:
    from serialcables_hydra import JBOFController


@dataclass
class HYDRAPacketResult:
    """Result from HYDRA packet transmission with timing data."""

    success: bool
    packets_sent: int
    response_bytes: bytes
    raw_response: str
    latency_ms: float = 0.0


class HYDRATransport:
    """
    Transport adapter wrapping serialcables-hydra JBOFController.

    Uses JBOFController.send_mctp_packet() for MCTP-over-SMBus
    communication with NVMe devices.

    Attributes:
        jbof: The underlying JBOFController instance
        slot: Current target slot (1-8)
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
        jbof: JBOFController,
        slot: int = 1,
        timeout: float = 2.0,
        verbose: bool = False,
    ):
        """
        Initialize HYDRA transport adapter.

        Args:
            jbof: Connected JBOFController instance
            slot: Initial target slot (1-8)
            timeout: Response timeout in seconds
            verbose: Print TX/RX packets
        """
        self._jbof = jbof
        self._slot = slot
        self._timeout = timeout
        self._verbose = verbose

        # Track last result for diagnostics
        self._last_result: HYDRAPacketResult | None = None

    @property
    def jbof(self) -> JBOFController:
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

    @property
    def last_result(self) -> HYDRAPacketResult | None:
        """Get the last packet transmission result."""
        return self._last_result

    def send_packet(self, packet: bytes) -> bytes:
        """
        Send MCTP packet and receive response.

        Uses JBOFController.send_mctp_packet() for transmission.

        Args:
            packet: Complete MCTP-over-SMBus packet bytes
                    Format: [Addr][Cmd=0x0F][ByteCount][MCTP...][PEC]

        Returns:
            Response packet bytes

        Raises:
            TransportError: On communication failure
            TimeoutError: If response times out
        """
        import time

        if len(packet) < 4:
            raise TransportError(f"Packet too short: {len(packet)} bytes")

        # Convert bytes to list of ints for the API
        mctp_frame = list(packet)

        if self._verbose:
            print(f"[HYDRATransport] TX slot={self._slot}: {packet.hex(' ')}")

        # Send packet using new API
        start_time = time.perf_counter()

        try:
            result = self._jbof.send_mctp_packet(
                dest_eid=self._slot,
                mctp_frame=mctp_frame,
                timeout=self._timeout,
            )
        except Exception as e:
            raise TransportError(f"Failed to send packet: {e}") from e

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Process response
        if not result.success:
            self._last_result = HYDRAPacketResult(
                success=False,
                packets_sent=result.packets_sent,
                response_bytes=b"",
                raw_response=result.raw_response,
                latency_ms=elapsed_ms,
            )
            raise CommunicationError(f"MCTP send failed: {result.raw_response}")

        # Extract response bytes from response_packets
        if not result.response_packets:
            self._last_result = HYDRAPacketResult(
                success=False,
                packets_sent=result.packets_sent,
                response_bytes=b"",
                raw_response=result.raw_response,
                latency_ms=elapsed_ms,
            )
            raise TimeoutError("No response packets received")

        # Concatenate all response packets (for fragmented responses)
        response_bytes = b""
        for pkt in result.response_packets:
            response_bytes += bytes(pkt)

        self._last_result = HYDRAPacketResult(
            success=True,
            packets_sent=result.packets_sent,
            response_bytes=response_bytes,
            raw_response=result.raw_response,
            latency_ms=elapsed_ms,
        )

        if self._verbose:
            print(f"[HYDRATransport] RX ({elapsed_ms:.2f}ms): {response_bytes.hex(' ')}")

        return response_bytes

    def send_packet_with_result(self, packet: bytes) -> HYDRAPacketResult:
        """
        Send packet and return detailed result including timing.

        Args:
            packet: Complete MCTP packet bytes

        Returns:
            HYDRAPacketResult with full details
        """
        try:
            self.send_packet(packet)
        except TransportError:
            pass  # Result captured in _last_result

        return self._last_result

    def set_target(
        self,
        slot: int | None = None,
        address: int | None = None,
    ) -> None:
        """
        Configure target slot.

        Args:
            slot: Target slot number (1-8)
            address: Ignored (address is in packet)
        """
        if slot is not None:
            self.slot = slot

    # =========================================================================
    # Convenience methods exposing JBOFController functionality
    # =========================================================================

    def get_slot_info(self) -> dict:
        """Get information about current slot."""
        return self._jbof.show_slot_info(self._slot)

    def get_all_slots_info(self) -> list[dict]:
        """Get information about all slots."""
        return [self._jbof.show_slot_info(i) for i in range(1, 9)]

    def power_on_slot(self, slot: int | None = None) -> bool:
        """Power on a slot."""
        target = slot or self._slot
        return self._jbof.slot_power(target, on=True)

    def power_off_slot(self, slot: int | None = None) -> bool:
        """Power off a slot."""
        target = slot or self._slot
        return self._jbof.slot_power(target, on=False)

    def reset_slot(self, slot: int | None = None) -> bool:
        """Reset SSD in slot."""
        target = slot or self._slot
        return self._jbof.ssd_reset(target)

    def smbus_reset(self) -> bool:
        """Reset SMBus interface."""
        return self._jbof.smbus_reset()

    # =========================================================================
    # MCTP Firmware Shortcuts (requires HYDRA firmware v0.0.6+)
    # =========================================================================

    def get_serial_number(self, slot: int | None = None, timeout: float | None = None):
        """
        Get NVMe drive serial number via firmware shortcut.

        Uses 'mctp <slot> sn' command (requires firmware v0.0.6+).

        Args:
            slot: Slot number (default: current slot)
            timeout: Optional timeout override

        Returns:
            NVMeSerialNumber from serialcables-hydra
        """
        target = slot or self._slot
        return self._jbof.mctp_get_serial_number(slot=target, timeout=timeout or self._timeout)

    def get_health_status(self, slot: int | None = None, timeout: float | None = None):
        """
        Get NVMe drive health status via firmware shortcut.

        Uses 'mctp <slot> health' command (requires firmware v0.0.6+).

        Args:
            slot: Slot number (default: current slot)
            timeout: Optional timeout override

        Returns:
            NVMeHealthStatus from serialcables-hydra
        """
        target = slot or self._slot
        return self._jbof.mctp_get_health_status(slot=target, timeout=timeout or self._timeout)

    # =========================================================================
    # MCTP Session Control (requires HYDRA firmware v1.3+)
    # =========================================================================

    def mctp_pause(self, slot: int | None = None, timeout: float | None = None):
        """
        Pause MCTP communication on a slot.

        Uses 'mctp <slot> pause' command. Pauses ongoing MCTP transactions,
        useful for debugging or when device needs time to process.

        Args:
            slot: Slot number (default: current slot)
            timeout: Optional timeout override

        Returns:
            MCTPResponse from serialcables-hydra
        """
        target = slot or self._slot
        return self._jbof.mctp_pause(slot=target, timeout=timeout or self._timeout)

    def mctp_resume(self, slot: int | None = None, timeout: float | None = None):
        """
        Resume MCTP communication on a slot.

        Uses 'mctp <slot> resume' command. Resumes paused MCTP transactions.

        Args:
            slot: Slot number (default: current slot)
            timeout: Optional timeout override

        Returns:
            MCTPResponse from serialcables-hydra
        """
        target = slot or self._slot
        return self._jbof.mctp_resume(slot=target, timeout=timeout or self._timeout)

    def mctp_abort(self, slot: int | None = None, timeout: float | None = None):
        """
        Abort MCTP communication on a slot.

        Uses 'mctp <slot> abort' command. Aborts any ongoing MCTP transaction
        and resets the MCTP state machine for the slot.

        Args:
            slot: Slot number (default: current slot)
            timeout: Optional timeout override

        Returns:
            MCTPResponse from serialcables-hydra
        """
        target = slot or self._slot
        return self._jbof.mctp_abort(slot=target, timeout=timeout or self._timeout)

    def mctp_status(self, slot: int | None = None, timeout: float | None = None):
        """
        Get MCTP status for a slot.

        Uses 'mctp <slot> status' command. Returns the current state of
        MCTP communication including any pending transactions or errors.

        Args:
            slot: Slot number (default: current slot)
            timeout: Optional timeout override

        Returns:
            MCTPResponse from serialcables-hydra with status information
        """
        target = slot or self._slot
        return self._jbof.mctp_status(slot=target, timeout=timeout or self._timeout)

    def mctp_replay(self, slot: int | None = None, timeout: float | None = None):
        """
        Replay the last MCTP transaction on a slot.

        Uses 'mctp <slot> replay' command. Re-sends the last MCTP packet
        that was transmitted to the slot. Useful for debugging or retrying
        failed transactions.

        Args:
            slot: Slot number (default: current slot)
            timeout: Optional timeout override

        Returns:
            MCTPResponse from serialcables-hydra with the replayed response
        """
        target = slot or self._slot
        return self._jbof.mctp_replay(slot=target, timeout=timeout or self._timeout)


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
