"""
NVMe-MI constants and enumerations per NVMe-MI Specification.
"""

from enum import IntEnum, IntFlag


class NVMeMIMessageType(IntEnum):
    """
    NVMe-MI Message Types per NVMe-MI Spec Figure 5.

    These are the values in the NVMe-MI message type field,
    distinct from the MCTP message type (which is 0x04 for NVMe-MI).
    """

    CONTROL_PRIMITIVE = 0x0
    MI_COMMAND = 0x1
    MI_RESPONSE = 0x2
    # 0x3 reserved
    ADMIN_COMMAND = 0x4
    ADMIN_RESPONSE = 0x5
    # 0x6-0xF reserved


class NVMeDataStructureType(IntEnum):
    """
    Read NVMe-MI Data Structure types per NVMe-MI Spec Figure 18.

    Used with the Read NVMe-MI Data Structure command (opcode 0x00).
    """

    NVM_SUBSYSTEM_INFORMATION = 0x00
    PORT_INFORMATION = 0x01
    CONTROLLER_LIST = 0x02
    CONTROLLER_INFORMATION = 0x03
    OPTIONALLY_SUPPORTED_COMMANDS = 0x04
    MANAGEMENT_ENDPOINT_BUFFER_INFO = 0x05
    # 0x06-0xFF reserved


class ConfigurationIdentifier(IntEnum):
    """
    Configuration Set/Get identifiers per NVMe-MI Spec Figure 26.

    Used with Configuration Set (0x03) and Configuration Get (0x04) commands.
    """

    SMBUS_I2C_FREQUENCY = 0x01
    HEALTH_STATUS_CHANGE = 0x02
    MCTP_TRANSMISSION_UNIT = 0x03
    # 0x04-0xFF reserved or vendor specific


class CriticalWarningFlags(IntFlag):
    """
    Critical Warning bitmap flags from SMART / Health Status.

    These flags indicate various warning conditions.
    Multiple flags can be set simultaneously.
    """

    NONE = 0
    SPARE_BELOW_THRESHOLD = 1 << 0
    TEMPERATURE_EXCEEDED = 1 << 1
    RELIABILITY_DEGRADED = 1 << 2
    READ_ONLY_MODE = 1 << 3
    VOLATILE_BACKUP_FAILED = 1 << 4
    PMR_READ_ONLY = 1 << 5
    # Bits 6-7 reserved

    def decode(self) -> list[str]:
        """
        Return list of active warning strings.

        Returns:
            List of warning names that are set, or ["None"] if no warnings
        """
        warnings = []
        for flag in CriticalWarningFlags:
            if flag != CriticalWarningFlags.NONE and self & flag:
                name = flag.name or str(flag.value)
                warnings.append(name.replace("_", " ").title())
        return warnings if warnings else ["None"]

    def __str__(self) -> str:
        return ", ".join(self.decode())


class ShutdownStatus(IntEnum):
    """
    Shutdown Status (SHST) field values.
    """

    NORMAL = 0
    SHUTDOWN_IN_PROGRESS = 1
    SHUTDOWN_COMPLETE = 2
    # 3 reserved

    def __str__(self) -> str:
        names = {
            0: "Normal operation",
            1: "Shutdown in progress",
            2: "Shutdown complete",
        }
        return names.get(self.value, f"Reserved ({self.value})")


class TemperatureState(IntEnum):
    """
    Composite temperature state interpretation.
    """

    UNKNOWN = -1
    NORMAL = 0
    WARNING = 1  # Above warning threshold
    CRITICAL = 2  # Above critical threshold

    def __str__(self) -> str:
        icons = {-1: "?", 0: "✓", 1: "⚠", 2: "🔥"}
        return f"{icons.get(self.value, '?')} {self.name}"


# NVMe temperature conversion
KELVIN_OFFSET = 273  # Subtract from Kelvin to get Celsius


def kelvin_to_celsius(kelvin: int) -> int:
    """Convert temperature from Kelvin to Celsius."""
    return kelvin - KELVIN_OFFSET


def celsius_to_kelvin(celsius: int) -> int:
    """Convert temperature from Celsius to Kelvin."""
    return celsius + KELVIN_OFFSET
