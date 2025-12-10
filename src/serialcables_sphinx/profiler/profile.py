"""
Device profile data structures.

Defines the structure for storing captured device responses
that can be serialized to JSON and loaded into MockTransport.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class CommandCategory(str, Enum):
    """Categories of NVMe-MI commands."""

    HEALTH = "health"
    DATA_STRUCTURE = "data_structure"
    CONFIGURATION = "configuration"
    VPD = "vpd"
    ADMIN_TUNNELED = "admin_tunneled"
    VENDOR_SPECIFIC = "vendor_specific"


@dataclass
class CapturedCommand:
    """
    A single captured command/response pair.

    Stores both the request and response for replay.
    """

    # Command identification
    opcode: int
    opcode_name: str
    category: str

    # Request details
    request_data: list[int]  # Additional request parameters
    eid: int

    # Response
    success: bool
    status_code: int
    status_name: str
    response_raw: list[int]  # Complete raw response bytes
    response_payload: list[int]  # NVMe-MI payload only

    # Timing
    latency_ms: float
    timestamp: str

    # Decoded fields (for verification)
    decoded_fields: dict[str, Any] = field(default_factory=dict)

    # For data structure commands
    data_type: int | None = None
    data_type_name: str | None = None

    # For configuration commands
    config_id: int | None = None
    config_id_name: str | None = None

    # For admin tunneled commands
    admin_opcode: int | None = None
    admin_opcode_name: str | None = None

    # Error info
    error: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> CapturedCommand:
        """Create from dictionary."""
        return cls(**data)


@dataclass
class ProfileMetadata:
    """
    Metadata about the profiled device and capture session.
    """

    # Capture info
    capture_date: str = ""
    capture_duration_seconds: float = 0.0
    sphinx_version: str = ""
    hydra_version: str = ""
    hydra_firmware_version: str | None = None

    # Device identification
    serial_number: str | None = None
    model_number: str | None = None
    firmware_revision: str | None = None
    vendor_id: int | None = None

    # Connection info
    port: str = ""
    slot: int = 1
    eid: int = 1

    # NVMe-MI capabilities
    nvme_mi_major_version: int | None = None
    nvme_mi_minor_version: int | None = None
    supported_commands: list[str] = field(default_factory=list)
    num_ports: int = 1
    num_controllers: int = 1
    controller_ids: list[int] = field(default_factory=list)

    # Capture statistics
    total_commands: int = 0
    successful_commands: int = 0
    failed_commands: int = 0
    unsupported_commands: list[str] = field(default_factory=list)

    # Timing statistics
    min_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    avg_latency_ms: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ProfileMetadata:
        """Create from dictionary."""
        return cls(**data)


@dataclass
class DeviceProfile:
    """
    Complete device profile with all captured responses.

    This is the main container that gets saved to JSON and
    loaded into MockTransport for replay.
    """

    # Profile identification
    profile_name: str
    profile_version: str = "1.0"

    # Metadata
    metadata: ProfileMetadata = field(default_factory=ProfileMetadata)

    # Captured commands organized by category
    health_commands: list[CapturedCommand] = field(default_factory=list)
    data_structure_commands: list[CapturedCommand] = field(default_factory=list)
    configuration_commands: list[CapturedCommand] = field(default_factory=list)
    vpd_commands: list[CapturedCommand] = field(default_factory=list)
    admin_tunneled_commands: list[CapturedCommand] = field(default_factory=list)
    vendor_commands: list[CapturedCommand] = field(default_factory=list)

    # Raw response lookup table: {opcode: {params_hash: response_bytes}}
    # For quick response lookup in MockTransport
    response_table: dict[str, dict[str, list[int]]] = field(default_factory=dict)

    # Checksum for integrity verification
    checksum: str | None = None

    def add_command(self, cmd: CapturedCommand) -> None:
        """Add a captured command to the appropriate list."""
        category = cmd.category

        if category == CommandCategory.HEALTH.value:
            self.health_commands.append(cmd)
        elif category == CommandCategory.DATA_STRUCTURE.value:
            self.data_structure_commands.append(cmd)
        elif category == CommandCategory.CONFIGURATION.value:
            self.configuration_commands.append(cmd)
        elif category == CommandCategory.VPD.value:
            self.vpd_commands.append(cmd)
        elif category == CommandCategory.ADMIN_TUNNELED.value:
            self.admin_tunneled_commands.append(cmd)
        elif category == CommandCategory.VENDOR_SPECIFIC.value:
            self.vendor_commands.append(cmd)

        # Update response table for MockTransport lookup
        self._update_response_table(cmd)

    def _update_response_table(self, cmd: CapturedCommand) -> None:
        """Update the response lookup table."""
        # Key is opcode as string
        opcode_key = f"0x{cmd.opcode:02X}"

        if opcode_key not in self.response_table:
            self.response_table[opcode_key] = {}

        # Params hash for distinguishing different requests with same opcode
        params_hash = self._hash_request_params(cmd)
        self.response_table[opcode_key][params_hash] = cmd.response_raw

    def _hash_request_params(self, cmd: CapturedCommand) -> str:
        """Create hash of request parameters for lookup."""
        params = {
            "data": cmd.request_data,
            "eid": cmd.eid,
            "data_type": cmd.data_type,
            "config_id": cmd.config_id,
            "admin_opcode": cmd.admin_opcode,
        }
        params_str = json.dumps(params, sort_keys=True)
        return hashlib.md5(params_str.encode()).hexdigest()[:8]

    def get_all_commands(self) -> list[CapturedCommand]:
        """Get all captured commands as a flat list."""
        return (
            self.health_commands
            + self.data_structure_commands
            + self.configuration_commands
            + self.vpd_commands
            + self.admin_tunneled_commands
            + self.vendor_commands
        )

    def get_response(
        self,
        opcode: int,
        request_data: list[int] = None,
        data_type: int = None,
        config_id: int = None,
    ) -> list[int] | None:
        """
        Look up a captured response by opcode and parameters.

        Used by MockTransport for replay.
        """
        opcode_key = f"0x{opcode:02X}"

        if opcode_key not in self.response_table:
            return None

        # Create a dummy command for hashing
        dummy = CapturedCommand(
            opcode=opcode,
            opcode_name="",
            category="",
            request_data=request_data or [],
            eid=1,
            success=True,
            status_code=0,
            status_name="",
            response_raw=[],
            response_payload=[],
            latency_ms=0,
            timestamp="",
            data_type=data_type,
            config_id=config_id,
        )

        params_hash = self._hash_request_params(dummy)
        return self.response_table[opcode_key].get(params_hash)

    def calculate_checksum(self) -> str:
        """Calculate checksum of profile content."""
        # Serialize without checksum
        data = self.to_dict()
        data.pop("checksum", None)
        content = json.dumps(data, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def verify_checksum(self) -> bool:
        """Verify profile integrity."""
        if not self.checksum:
            return True
        return self.calculate_checksum() == self.checksum

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "profile_name": self.profile_name,
            "profile_version": self.profile_version,
            "metadata": self.metadata.to_dict(),
            "health_commands": [c.to_dict() for c in self.health_commands],
            "data_structure_commands": [c.to_dict() for c in self.data_structure_commands],
            "configuration_commands": [c.to_dict() for c in self.configuration_commands],
            "vpd_commands": [c.to_dict() for c in self.vpd_commands],
            "admin_tunneled_commands": [c.to_dict() for c in self.admin_tunneled_commands],
            "vendor_commands": [c.to_dict() for c in self.vendor_commands],
            "response_table": self.response_table,
            "checksum": self.checksum,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DeviceProfile:
        """Create from dictionary."""
        profile = cls(
            profile_name=data["profile_name"],
            profile_version=data.get("profile_version", "1.0"),
            metadata=ProfileMetadata.from_dict(data.get("metadata", {})),
            checksum=data.get("checksum"),
        )

        # Load commands
        for cmd_data in data.get("health_commands", []):
            profile.health_commands.append(CapturedCommand.from_dict(cmd_data))
        for cmd_data in data.get("data_structure_commands", []):
            profile.data_structure_commands.append(CapturedCommand.from_dict(cmd_data))
        for cmd_data in data.get("configuration_commands", []):
            profile.configuration_commands.append(CapturedCommand.from_dict(cmd_data))
        for cmd_data in data.get("vpd_commands", []):
            profile.vpd_commands.append(CapturedCommand.from_dict(cmd_data))
        for cmd_data in data.get("admin_tunneled_commands", []):
            profile.admin_tunneled_commands.append(CapturedCommand.from_dict(cmd_data))
        for cmd_data in data.get("vendor_commands", []):
            profile.vendor_commands.append(CapturedCommand.from_dict(cmd_data))

        # Load response table
        profile.response_table = data.get("response_table", {})

        return profile

    def save(self, filepath: str, indent: int = 2) -> None:
        """
        Save profile to JSON file.

        Args:
            filepath: Path to save to
            indent: JSON indentation (None for compact)
        """
        # Calculate checksum before saving
        self.checksum = self.calculate_checksum()

        with open(filepath, "w") as f:
            json.dump(self.to_dict(), f, indent=indent)

        print(f"Profile saved to: {filepath}")
        print(f"  Commands: {len(self.get_all_commands())}")
        print(f"  Checksum: {self.checksum}")

    @classmethod
    def load(cls, filepath: str) -> DeviceProfile:
        """
        Load profile from JSON file.

        Args:
            filepath: Path to load from

        Returns:
            Loaded DeviceProfile
        """
        with open(filepath) as f:
            data = json.load(f)

        profile = cls.from_dict(data)

        # Verify checksum
        if not profile.verify_checksum():
            print("WARNING: Profile checksum mismatch - file may be corrupted")

        return profile

    def summary(self) -> str:
        """Generate a summary string."""
        lines = [
            f"Device Profile: {self.profile_name}",
            "=" * 60,
            f"Device: {self.metadata.model_number or 'Unknown'}",
            f"Serial: {self.metadata.serial_number or 'Unknown'}",
            f"Firmware: {self.metadata.firmware_revision or 'Unknown'}",
            f"NVMe-MI Version: {self.metadata.nvme_mi_major_version}.{self.metadata.nvme_mi_minor_version}",
            "",
            "Captured Commands:",
            f"  Health:       {len(self.health_commands)}",
            f"  Data Struct:  {len(self.data_structure_commands)}",
            f"  Config:       {len(self.configuration_commands)}",
            f"  VPD:          {len(self.vpd_commands)}",
            f"  Admin Tunnel: {len(self.admin_tunneled_commands)}",
            f"  Vendor:       {len(self.vendor_commands)}",
            f"  Total:        {len(self.get_all_commands())}",
            "",
            f"Timing (ms): min={self.metadata.min_latency_ms:.2f}, "
            f"max={self.metadata.max_latency_ms:.2f}, "
            f"avg={self.metadata.avg_latency_ms:.2f}",
        ]

        if self.metadata.unsupported_commands:
            lines.append("")
            lines.append(f"Unsupported: {', '.join(self.metadata.unsupported_commands)}")

        return "\n".join(lines)
