"""
NVMe-MI decoded response container.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from serialcables_sphinx.nvme_mi.opcodes import NVMeMIOpcode
from serialcables_sphinx.nvme_mi.status import NVMeMIStatus


@dataclass
class DecodedField:
    """
    A single decoded field with metadata.

    Captures the parsed value along with the raw bytes and
    additional context for debugging and display.

    Attributes:
        name: Human-readable field name
        value: Parsed/decoded value
        raw: Original raw bytes for this field
        unit: Unit of measurement (e.g., "°C", "%", "bytes")
        description: Additional context or interpretation
    """

    name: str
    value: Any
    raw: bytes
    unit: str = ""
    description: str = ""

    def __str__(self) -> str:
        unit_str = f" {self.unit}" if self.unit else ""
        return f"{self.name}: {self.value}{unit_str}"

    def to_dict(self) -> dict:
        """Export field as dictionary."""
        return {
            "name": self.name,
            "value": self.value,
            "raw_hex": self.raw.hex() if self.raw else "",
            "unit": self.unit,
            "description": self.description,
        }


@dataclass
class DecodedResponse:
    """
    Container for decoded NVMe-MI response.

    Holds both the raw response data and all parsed fields,
    providing multiple output formats for different use cases.

    Attributes:
        opcode: The opcode that was sent
        status: Response status value
        raw_data: Complete raw response bytes
        fields: Dictionary of decoded fields by name
        timestamp: When the response was received
        decode_errors: Any errors or warnings during decoding

    Example:
        result = sphinx.nvme_mi.health_status_poll(eid=1)

        # Check success
        if result.success:
            # Access fields directly
            temp = result['Composite Temperature']
            spare = result.get('Available Spare', 'N/A')

            # Pretty print for debugging
            print(result.pretty_print())

            # Export for JSON API
            data = result.to_dict()
    """

    opcode: int | NVMeMIOpcode
    status: int | NVMeMIStatus
    raw_data: bytes
    fields: dict[str, DecodedField] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    decode_errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Check if response indicates success."""
        status_val = self.status.value if isinstance(self.status, NVMeMIStatus) else self.status
        return status_val == NVMeMIStatus.SUCCESS

    @property
    def status_code(self) -> int:
        """Get raw status code value."""
        return self.status.value if isinstance(self.status, NVMeMIStatus) else self.status

    @property
    def opcode_value(self) -> int:
        """Get raw opcode value."""
        return self.opcode.value if isinstance(self.opcode, NVMeMIOpcode) else self.opcode

    def __getitem__(self, key: str) -> Any:
        """
        Allow dict-like access to field values.

        Args:
            key: Field name

        Returns:
            Field value

        Raises:
            KeyError: If field not found
        """
        return self.fields[key].value

    def get(self, key: str, default: Any = None) -> Any:
        """
        Safe field value access.

        Args:
            key: Field name
            default: Value to return if field not found

        Returns:
            Field value or default
        """
        if key in self.fields:
            return self.fields[key].value
        return default

    def has_field(self, key: str) -> bool:
        """Check if a field exists."""
        return key in self.fields

    def get_field(self, key: str) -> DecodedField | None:
        """Get full DecodedField object by name."""
        return self.fields.get(key)

    @property
    def field_names(self) -> list[str]:
        """Get list of all field names."""
        return list(self.fields.keys())

    def summary(self) -> str:
        """
        One-line summary of the response.

        Returns:
            Short status string like "[✓] HEALTH_STATUS_POLL: SUCCESS (0x00)"
        """
        status_icon = "✓" if self.success else "✗"
        opcode_name = NVMeMIOpcode.decode(self.opcode_value)
        status_str = NVMeMIStatus.decode(self.status_code)
        return f"[{status_icon}] {opcode_name}: {status_str}"

    def pretty_print(self, indent: int = 0) -> str:
        """
        Human-readable formatted output.

        Args:
            indent: Number of indentation levels

        Returns:
            Multi-line formatted string
        """
        prefix = "  " * indent
        sep = "═" * 60
        thin_sep = "─" * 60

        opcode_name = NVMeMIOpcode.decode(self.opcode_value)
        status_str = NVMeMIStatus.decode(self.status_code)

        lines = [
            f"{prefix}{sep}",
            f"{prefix}NVMe-MI Response: {opcode_name}",
            f"{prefix}{sep}",
            f"{prefix}Status: {status_str}",
            f"{prefix}Timestamp: {self.timestamp.isoformat()}",
            f"{prefix}Raw Data ({len(self.raw_data)} bytes): {self.raw_data.hex()}",
            f"{prefix}{thin_sep}",
        ]

        if self.fields:
            lines.append(f"{prefix}Decoded Fields:")
            max_name_len = max(len(f.name) for f in self.fields.values())

            for fld in self.fields.values():
                unit_str = f" {fld.unit}" if fld.unit else ""
                lines.append(f"{prefix}  {fld.name:<{max_name_len}} : {fld.value}{unit_str}")
                if fld.description:
                    lines.append(f"{prefix}  {' ' * max_name_len}   └─ {fld.description}")

        if self.decode_errors:
            lines.append(f"{prefix}{thin_sep}")
            lines.append(f"{prefix}Decode Warnings:")
            for err in self.decode_errors:
                lines.append(f"{prefix}  ⚠ {err}")

        lines.append(f"{prefix}{sep}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """
        Export as dictionary for JSON serialization.

        Returns:
            Dictionary with all response data
        """
        return {
            "opcode": NVMeMIOpcode.decode(self.opcode_value),
            "opcode_value": self.opcode_value,
            "status": NVMeMIStatus.decode(self.status_code),
            "status_value": self.status_code,
            "success": self.success,
            "timestamp": self.timestamp.isoformat(),
            "raw_data_hex": self.raw_data.hex(),
            "fields": {k: v.to_dict() for k, v in self.fields.items()},
            "decode_errors": self.decode_errors,
        }

    def to_flat_dict(self) -> dict:
        """
        Export as flat dictionary with just field values.

        Useful for simple data extraction without metadata.

        Returns:
            Dictionary mapping field names to values
        """
        result = {
            "success": self.success,
            "status": self.status_code,
        }
        for name, fld in self.fields.items():
            result[name] = fld.value
        return result

    def __repr__(self) -> str:
        return f"DecodedResponse({self.summary()}, fields={len(self.fields)})"
