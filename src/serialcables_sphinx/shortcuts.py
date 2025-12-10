"""
MCTP Firmware Shortcut Commands

Provides high-level access to HYDRA firmware's built-in MCTP commands
that simplify common operations like getting serial numbers and health status.

These shortcuts use firmware-level commands (mctp <slot> sn, mctp <slot> health)
that handle the MCTP protocol internally, returning pre-parsed data along with
raw packets for full decoding.

The module bridges these firmware responses to Sphinx's decoder infrastructure,
giving users both quick-access values and fully decoded NVMe-MI responses.

Available Shortcuts (HYDRA firmware v0.0.6+):
- Serial Number: mctp <slot> sn
- Health Status: mctp <slot> health

Example:
    from serialcables_hydra import JBOFController
    from serialcables_sphinx.shortcuts import MCTPShortcuts

    jbof = JBOFController(port="COM13")
    shortcuts = MCTPShortcuts(jbof)

    # Quick access to serial number
    result = shortcuts.get_serial_number(slot=1)
    print(f"Serial: {result.serial_number}")

    # Full decoded health status
    result = shortcuts.get_health_status(slot=1)
    print(result.decoded.pretty_print())  # Full Sphinx decoding
    print(f"Quick temp: {result.temperature_celsius}°C")  # Firmware-parsed value
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from serialcables_hydra import JBOFController

from serialcables_sphinx.nvme_mi.decoder import NVMeMIDecoder
from serialcables_sphinx.nvme_mi.opcodes import NVMeMIOpcode
from serialcables_sphinx.nvme_mi.response import DecodedResponse


class MCTPShortcutCommand(Enum):
    """Available MCTP firmware shortcut commands."""

    SERIAL_NUMBER = "sn"
    HEALTH_STATUS = "health"
    # Future commands can be added here
    # IDENTIFY = "id"
    # LOG_PAGE = "log"


@dataclass
class SerialNumberResult:
    """
    Result from MCTP serial number query.

    Combines firmware-parsed data with optional full Sphinx decoding.
    """

    # Quick-access values (from firmware parsing)
    slot: int
    serial_number: str
    success: bool
    error: str | None = None

    # Raw data for inspection
    raw_packets: list[list[int]] = field(default_factory=list)

    # Full Sphinx decoding (if raw packets available)
    decoded: DecodedResponse | None = None

    def __str__(self) -> str:
        if self.success:
            return f"Slot {self.slot}: {self.serial_number}"
        return f"Slot {self.slot}: Error - {self.error}"


@dataclass
class HealthStatusResult:
    """
    Result from MCTP health status query.

    Combines firmware-parsed data with full Sphinx decoding.
    """

    # Quick-access values (from firmware parsing)
    slot: int
    success: bool
    temperature_kelvin: int | None = None
    temperature_celsius: float | None = None
    available_spare: int | None = None
    spare_threshold: int | None = None
    percentage_used: int | None = None
    critical_warning: int | None = None
    error: str | None = None

    # Raw data for inspection
    raw_packets: list[list[int]] = field(default_factory=list)

    # Full Sphinx decoding
    decoded: DecodedResponse | None = None

    @property
    def is_healthy(self) -> bool:
        """Quick health check - no critical warnings and spare > threshold."""
        if not self.success:
            return False
        if self.critical_warning and self.critical_warning != 0:
            return False
        if self.available_spare is not None and self.spare_threshold is not None:
            if self.available_spare <= self.spare_threshold:
                return False
        return True

    def summary(self) -> str:
        """One-line health summary."""
        if not self.success:
            return f"Slot {self.slot}: Error - {self.error}"

        parts = []
        if self.temperature_celsius is not None:
            parts.append(f"{self.temperature_celsius:.0f}°C")
        if self.available_spare is not None:
            parts.append(f"Spare:{self.available_spare}%")
        if self.percentage_used is not None:
            parts.append(f"Used:{self.percentage_used}%")
        if self.critical_warning:
            parts.append(f"⚠ Warning:0x{self.critical_warning:02X}")

        status = "✓" if self.is_healthy else "⚠"
        return f"[{status}] Slot {self.slot}: " + " | ".join(parts)

    def __str__(self) -> str:
        return self.summary()


@dataclass
class ShortcutResult:
    """
    Generic result for future shortcut commands.

    Provides a common structure for any MCTP shortcut response.
    """

    command: MCTPShortcutCommand
    slot: int
    success: bool
    raw_packets: list[list[int]] = field(default_factory=list)
    decoded: DecodedResponse | None = None
    parsed_data: dict = field(default_factory=dict)
    error: str | None = None


class MCTPShortcuts:
    """
    High-level interface to HYDRA firmware MCTP shortcut commands.

    Wraps JBOFController's mctp_* methods and provides:
    - Quick-access parsed values from firmware
    - Full Sphinx decoding of raw response packets
    - Consistent result structures

    Attributes:
        jbof: The JBOFController instance
        decoder: Sphinx NVMe-MI decoder for full response parsing
        timeout: Default timeout for MCTP operations

    Example:
        from serialcables_hydra import JBOFController
        from serialcables_sphinx.shortcuts import MCTPShortcuts

        jbof = JBOFController(port="/dev/ttyUSB0")
        shortcuts = MCTPShortcuts(jbof)

        # Get serial number
        sn = shortcuts.get_serial_number(slot=1)
        if sn.success:
            print(f"Serial: {sn.serial_number}")

        # Get health with full decoding
        health = shortcuts.get_health_status(slot=1)
        if health.success:
            print(f"Temperature: {health.temperature_celsius}°C")
            if health.decoded:
                print(health.decoded.pretty_print())
    """

    def __init__(
        self,
        jbof: JBOFController,
        timeout: float = 3.0,
        decode_responses: bool = True,
    ):
        """
        Initialize MCTP shortcuts.

        Args:
            jbof: Connected JBOFController instance
            timeout: Default timeout for MCTP operations (seconds)
            decode_responses: Whether to decode raw packets with Sphinx
        """
        self._jbof = jbof
        self._timeout = timeout
        self._decode_responses = decode_responses
        self._decoder = NVMeMIDecoder() if decode_responses else None

    @property
    def jbof(self) -> JBOFController:
        """Get underlying JBOFController."""
        return self._jbof

    def get_serial_number(
        self,
        slot: int,
        timeout: float | None = None,
    ) -> SerialNumberResult:
        """
        Get NVMe drive serial number via firmware shortcut.

        Uses 'mctp <slot> sn' command.

        Args:
            slot: Slot number (1-8)
            timeout: Optional timeout override

        Returns:
            SerialNumberResult with serial number and optional decoding
        """
        timeout = timeout or self._timeout

        # Call firmware command
        response = self._jbof.mctp_get_serial_number(slot=slot, timeout=timeout)

        # Build result
        result = SerialNumberResult(
            slot=response.slot,
            serial_number=response.serial_number,
            success=response.success,
            error=response.error,
            raw_packets=response.raw_packets,
        )

        # Decode raw packets if available and decoding enabled
        if self._decode_responses and response.raw_packets:
            result.decoded = self._decode_raw_packets(
                response.raw_packets,
                opcode=NVMeMIOpcode.READ_NVME_MI_DATA_STRUCTURE,
            )

        return result

    def get_health_status(
        self,
        slot: int,
        timeout: float | None = None,
    ) -> HealthStatusResult:
        """
        Get NVMe drive health status via firmware shortcut.

        Uses 'mctp <slot> health' command.

        Args:
            slot: Slot number (1-8)
            timeout: Optional timeout override

        Returns:
            HealthStatusResult with health data and full Sphinx decoding
        """
        timeout = timeout or self._timeout

        # Call firmware command
        response = self._jbof.mctp_get_health_status(slot=slot, timeout=timeout)

        # Build result with firmware-parsed values
        result = HealthStatusResult(
            slot=response.slot,
            success=response.success,
            temperature_kelvin=response.composite_temperature,
            temperature_celsius=response.composite_temperature_celsius,
            available_spare=response.available_spare,
            spare_threshold=response.available_spare_threshold,
            percentage_used=response.percentage_used,
            critical_warning=response.critical_warning,
            error=response.error,
            raw_packets=response.raw_packets,
        )

        # Decode raw packets for full details
        if self._decode_responses and response.raw_packets:
            result.decoded = self._decode_raw_packets(
                response.raw_packets,
                opcode=NVMeMIOpcode.NVM_SUBSYSTEM_HEALTH_STATUS_POLL,
            )

        return result

    def _decode_raw_packets(
        self,
        raw_packets: list[list[int]],
        opcode: int,
    ) -> DecodedResponse | None:
        """
        Decode raw MCTP response packets using Sphinx.

        Args:
            raw_packets: List of packet byte arrays from firmware
            opcode: NVMe-MI opcode for decoder selection

        Returns:
            DecodedResponse or None if decoding fails
        """
        if not self._decoder or not raw_packets:
            return None

        try:
            # Concatenate all packets (for fragmented responses)
            all_bytes = []
            for pkt in raw_packets:
                all_bytes.extend(pkt)

            response_bytes = bytes(all_bytes)

            # Extract NVMe-MI payload from MCTP framing
            # Format: [SMBus: 3][MCTP Header: 4][MsgType: 1][NVMe-MI payload...][PEC: 1]
            if len(response_bytes) < 9:
                return None

            # Get byte count to find payload
            byte_count = response_bytes[2]

            # NVMe-MI payload starts at offset 8 (after SMBus + MCTP header + msg type)
            # and ends before PEC
            nvme_mi_start = 8
            nvme_mi_end = 3 + byte_count  # SMBus header + byte_count bytes

            if nvme_mi_end > len(response_bytes):
                nvme_mi_end = len(response_bytes) - 1  # Exclude PEC

            nvme_mi_payload = response_bytes[nvme_mi_start:nvme_mi_end]

            # Decode with Sphinx
            return self._decoder.decode_response(nvme_mi_payload, opcode)

        except Exception as e:
            # Return partial result on decode error
            return DecodedResponse(
                opcode=opcode,
                status=0xFF,
                raw_data=bytes(raw_packets[0]) if raw_packets else b"",
                decode_errors=[f"Decode failed: {e}"],
            )

    # =========================================================================
    # Batch Operations
    # =========================================================================

    def scan_all_slots(
        self,
        timeout: float | None = None,
    ) -> list[SerialNumberResult]:
        """
        Scan all slots for NVMe drives.

        Args:
            timeout: Optional timeout per slot

        Returns:
            List of SerialNumberResult for slots 1-8
        """
        results = []
        for slot in range(1, 9):
            try:
                result = self.get_serial_number(slot=slot, timeout=timeout)
                results.append(result)
            except Exception as e:
                results.append(
                    SerialNumberResult(
                        slot=slot,
                        serial_number="",
                        success=False,
                        error=str(e),
                    )
                )
        return results

    def health_check_all_slots(
        self,
        timeout: float | None = None,
    ) -> list[HealthStatusResult]:
        """
        Get health status for all slots.

        Args:
            timeout: Optional timeout per slot

        Returns:
            List of HealthStatusResult for slots 1-8
        """
        results = []
        for slot in range(1, 9):
            try:
                result = self.get_health_status(slot=slot, timeout=timeout)
                results.append(result)
            except Exception as e:
                results.append(
                    HealthStatusResult(
                        slot=slot,
                        success=False,
                        error=str(e),
                    )
                )
        return results

    def print_health_summary(
        self,
        slots: list[int] | None = None,
        timeout: float | None = None,
    ) -> None:
        """
        Print health summary for specified slots.

        Args:
            slots: List of slot numbers (default: all 1-8)
            timeout: Optional timeout per slot
        """
        slots = slots or list(range(1, 9))

        print("=" * 60)
        print("NVMe Health Summary")
        print("=" * 60)

        for slot in slots:
            try:
                result = self.get_health_status(slot=slot, timeout=timeout)
                print(result.summary())
            except Exception as e:
                print(f"[✗] Slot {slot}: Error - {e}")

        print("=" * 60)


# Convenience function for quick access
def create_shortcuts(
    port: str,
    timeout: float = 3.0,
) -> MCTPShortcuts:
    """
    Create MCTPShortcuts with connected JBOFController.

    Args:
        port: Serial port (e.g., "/dev/ttyUSB0", "COM13")
        timeout: Default MCTP timeout

    Returns:
        MCTPShortcuts instance ready to use

    Example:
        shortcuts = create_shortcuts("COM13")
        health = shortcuts.get_health_status(slot=1)
    """
    from serialcables_hydra import JBOFController

    jbof = JBOFController(port=port)
    return MCTPShortcuts(jbof, timeout=timeout)
