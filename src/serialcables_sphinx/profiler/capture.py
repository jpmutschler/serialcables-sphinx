"""
Device profiler capture module.

Captures NVMe-MI responses from a real device for MockTransport replay.
Only executes read-only commands to avoid damaging the device.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from serialcables_sphinx.nvme_mi.constants import (
    ConfigurationIdentifier,
    NVMeDataStructureType,
)
from serialcables_sphinx.nvme_mi.opcodes import NVMeMIOpcode
from serialcables_sphinx.nvme_mi.status import NVMeMIStatus
from serialcables_sphinx.profiler.profile import (
    CapturedCommand,
    CommandCategory,
    DeviceProfile,
    ProfileMetadata,
)


@dataclass
class CaptureConfig:
    """Configuration for profile capture."""

    # What to capture
    capture_health: bool = True
    capture_data_structures: bool = True
    capture_configuration: bool = True
    capture_vpd: bool = True
    capture_admin_tunneled: bool = True  # Identify, Get Log Page, Get Features

    # VPD settings
    vpd_max_offset: int = 4096
    vpd_chunk_size: int = 256

    # Timing
    command_delay_ms: float = 50.0  # Delay between commands
    timeout: float = 3.0  # Command timeout

    # Retry on failure
    retry_count: int = 2
    retry_delay_ms: float = 100.0

    # Verbosity
    verbose: bool = True
    progress_callback: Callable[[str, int, int], None] | None = None


class DeviceProfiler:
    """
    Profiles an NVMe device by capturing all read-only command responses.

    The captured responses can be used in MockTransport for testing
    without risk to the real device.

    Example:
        profiler = DeviceProfiler(port="COM13", slot=1)
        profile = profiler.capture_full_profile()
        profile.save("my_device.json")
    """

    def __init__(
        self,
        port: str,
        slot: int = 1,
        eid: int = 1,
        config: CaptureConfig | None = None,
    ):
        """
        Initialize profiler.

        Args:
            port: Serial port for HYDRA
            slot: Target slot number
            eid: Target endpoint ID
            config: Capture configuration
        """
        self._port = port
        self._slot = slot
        self._eid = eid
        self._config = config or CaptureConfig()

        # Will be initialized on capture
        self._jbof = None
        self._transport = None
        self._sphinx = None

        # Capture state
        self._profile: DeviceProfile | None = None
        self._start_time: float = 0
        self._latencies: list[float] = []

    def capture_full_profile(
        self,
        profile_name: str | None = None,
    ) -> DeviceProfile:
        """
        Capture a complete device profile.

        This runs all safe (read-only) NVMe-MI commands and captures
        the responses for later replay.

        Args:
            profile_name: Name for the profile (auto-generated if None)

        Returns:
            DeviceProfile with all captured responses
        """
        self._start_time = time.time()
        self._latencies = []

        # Connect to device
        self._connect()

        # Initialize profile
        if profile_name is None:
            profile_name = f"device_profile_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self._profile = DeviceProfile(profile_name=profile_name)
        self._profile.metadata = self._create_metadata()

        self._log(f"Starting device profile capture: {profile_name}")
        self._log(f"Port: {self._port}, Slot: {self._slot}, EID: {self._eid}")
        self._log("=" * 60)

        try:
            # Capture in order of importance
            if self._config.capture_health:
                self._capture_health_commands()

            if self._config.capture_data_structures:
                self._capture_data_structure_commands()

            if self._config.capture_configuration:
                self._capture_configuration_commands()

            if self._config.capture_vpd:
                self._capture_vpd_commands()

            if self._config.capture_admin_tunneled:
                self._capture_admin_tunneled_commands()

        except KeyboardInterrupt:
            self._log("\nCapture interrupted by user")
        except Exception as e:
            self._log(f"\nCapture error: {e}")
            raise
        finally:
            # Update final metadata
            self._finalize_metadata()
            self._disconnect()

        self._log("=" * 60)
        self._log("Capture complete!")
        self._log(self._profile.summary())

        return self._profile

    def _connect(self) -> None:
        """Connect to HYDRA and create Sphinx client."""
        try:
            from serialcables_hydra import JBOFController

            from serialcables_sphinx import Sphinx
            from serialcables_sphinx.transports.hydra import HYDRATransport
        except ImportError as e:
            raise ImportError(f"Required modules not available: {e}") from e

        self._log(f"Connecting to HYDRA on {self._port}...")

        self._jbof = JBOFController(port=self._port)
        self._jbof.connect()
        self._transport = HYDRATransport(
            self._jbof,
            slot=self._slot,
            timeout=self._config.timeout,
        )
        self._sphinx = Sphinx(self._transport)

        self._log("Connected successfully")

    def _disconnect(self) -> None:
        """Disconnect from HYDRA."""
        # JBOFController handles cleanup automatically
        self._sphinx = None
        self._transport = None
        self._jbof = None

    def _create_metadata(self) -> ProfileMetadata:
        """Create initial metadata."""
        import serialcables_sphinx

        try:
            import serialcables_hydra

            hydra_version = getattr(serialcables_hydra, "__version__", "unknown")
        except ImportError:
            hydra_version = "unknown"

        return ProfileMetadata(
            capture_date=datetime.now().isoformat(),
            capture_duration_seconds=0,
            sphinx_version=getattr(serialcables_sphinx, "__version__", "unknown"),
            hydra_version=hydra_version,
            port=self._port,
            slot=self._slot,
            eid=self._eid,
        )

    def _finalize_metadata(self) -> None:
        """Update metadata with final statistics."""
        meta = self._profile.metadata

        # Duration
        meta.capture_duration_seconds = time.time() - self._start_time

        # Command counts
        all_cmds = self._profile.get_all_commands()
        meta.total_commands = len(all_cmds)
        meta.successful_commands = sum(1 for c in all_cmds if c.success)
        meta.failed_commands = meta.total_commands - meta.successful_commands

        # Latency stats
        if self._latencies:
            meta.min_latency_ms = min(self._latencies)
            meta.max_latency_ms = max(self._latencies)
            meta.avg_latency_ms = sum(self._latencies) / len(self._latencies)

    def _capture_command(
        self,
        name: str,
        category: str,
        opcode: int,
        request_func: Callable,
        request_data: list[int] = None,
        data_type: int = None,
        config_id: int = None,
        admin_opcode: int = None,
    ) -> CapturedCommand | None:
        """
        Capture a single command response.

        Args:
            name: Human-readable command name
            category: Command category
            opcode: NVMe-MI opcode
            request_func: Function to call for the request
            request_data: Additional request parameters
            data_type: Data structure type (if applicable)
            config_id: Configuration ID (if applicable)
            admin_opcode: Admin opcode for tunneled commands

        Returns:
            CapturedCommand or None on failure
        """
        self._progress(f"  {name}...")

        # Wait between commands
        if self._config.command_delay_ms > 0:
            time.sleep(self._config.command_delay_ms / 1000.0)

        # Try with retries
        last_error = None
        for attempt in range(self._config.retry_count + 1):
            try:
                start = time.perf_counter()
                result = request_func()
                latency = (time.perf_counter() - start) * 1000

                self._latencies.append(latency)

                # Build captured command
                cmd = CapturedCommand(
                    opcode=opcode,
                    opcode_name=NVMeMIOpcode.decode(opcode),
                    category=category,
                    request_data=request_data or [],
                    eid=self._eid,
                    success=result.success,
                    status_code=result.status_code,
                    status_name=NVMeMIStatus.decode(result.status_code),
                    response_raw=list(result.raw_data),
                    response_payload=list(result.raw_data[4:]) if len(result.raw_data) > 4 else [],
                    latency_ms=latency,
                    timestamp=datetime.now().isoformat(),
                    decoded_fields={k: str(v.value) for k, v in result.fields.items()},
                    data_type=data_type,
                    data_type_name=(
                        NVMeDataStructureType(data_type).name if data_type is not None else None
                    ),
                    config_id=config_id,
                    admin_opcode=admin_opcode,
                )

                if result.success:
                    self._progress(f"  {name}... OK ({latency:.1f}ms)")
                else:
                    self._progress(f"  {name}... {cmd.status_name}")
                    if not result.success:
                        self._profile.metadata.unsupported_commands.append(name)

                self._profile.add_command(cmd)
                return cmd

            except Exception as e:
                last_error = str(e)
                if attempt < self._config.retry_count:
                    time.sleep(self._config.retry_delay_ms / 1000.0)

        # All retries failed
        self._progress(f"  {name}... FAILED: {last_error}")

        cmd = CapturedCommand(
            opcode=opcode,
            opcode_name=NVMeMIOpcode.decode(opcode),
            category=category,
            request_data=request_data or [],
            eid=self._eid,
            success=False,
            status_code=0xFF,
            status_name="COMMUNICATION_ERROR",
            response_raw=[],
            response_payload=[],
            latency_ms=0,
            timestamp=datetime.now().isoformat(),
            error=last_error,
            data_type=data_type,
            config_id=config_id,
            admin_opcode=admin_opcode,
        )

        self._profile.metadata.unsupported_commands.append(name)
        self._profile.add_command(cmd)
        return cmd

    def _capture_health_commands(self) -> None:
        """Capture health-related commands."""
        self._log("\n[Health Commands]")

        # NVM Subsystem Health Status Poll
        self._capture_command(
            name="NVM Subsystem Health Status Poll",
            category=CommandCategory.HEALTH.value,
            opcode=NVMeMIOpcode.NVM_SUBSYSTEM_HEALTH_STATUS_POLL,
            request_func=lambda: self._sphinx.nvme_mi.health_status_poll(eid=self._eid),
        )

        # Get controller list first
        ctrl_result = self._sphinx.nvme_mi.get_controller_list(eid=self._eid)
        if ctrl_result.success:
            controller_ids = ctrl_result.get("Controller IDs", [])
            self._profile.metadata.controller_ids = controller_ids
            self._profile.metadata.num_controllers = len(controller_ids)

            # Controller Health Status for each controller
            for ctrl_id in controller_ids:
                self._capture_command(
                    name=f"Controller {ctrl_id} Health Status",
                    category=CommandCategory.HEALTH.value,
                    opcode=NVMeMIOpcode.CONTROLLER_HEALTH_STATUS_POLL,
                    request_func=lambda cid=ctrl_id: self._sphinx.nvme_mi.controller_health_status(
                        cid, eid=self._eid
                    ),
                    request_data=[ctrl_id & 0xFF, (ctrl_id >> 8) & 0xFF],
                )

    def _capture_data_structure_commands(self) -> None:
        """Capture Read NVMe-MI Data Structure commands."""
        self._log("\n[Data Structure Commands]")

        # NVM Subsystem Information
        result = self._capture_command(
            name="NVM Subsystem Information",
            category=CommandCategory.DATA_STRUCTURE.value,
            opcode=NVMeMIOpcode.READ_NVME_MI_DATA_STRUCTURE,
            request_func=lambda: self._sphinx.nvme_mi.get_subsystem_info(eid=self._eid),
            data_type=NVMeDataStructureType.NVM_SUBSYSTEM_INFORMATION,
        )

        if result and result.success:
            # Extract NVMe-MI version
            self._profile.metadata.nvme_mi_major_version = result.decoded_fields.get(
                "NVMe-MI Major Version"
            )
            self._profile.metadata.nvme_mi_minor_version = result.decoded_fields.get(
                "NVMe-MI Minor Version"
            )
            num_ports = result.decoded_fields.get("Number of Ports")
            if num_ports:
                self._profile.metadata.num_ports = int(num_ports)

        # Port Information for each port
        for port_id in range(self._profile.metadata.num_ports):
            self._capture_command(
                name=f"Port {port_id} Information",
                category=CommandCategory.DATA_STRUCTURE.value,
                opcode=NVMeMIOpcode.READ_NVME_MI_DATA_STRUCTURE,
                request_func=lambda pid=port_id: self._sphinx.nvme_mi.get_port_info(
                    port_id=pid, eid=self._eid
                ),
                request_data=[NVMeDataStructureType.PORT_INFORMATION, port_id],
                data_type=NVMeDataStructureType.PORT_INFORMATION,
            )

        # Controller List
        self._capture_command(
            name="Controller List",
            category=CommandCategory.DATA_STRUCTURE.value,
            opcode=NVMeMIOpcode.READ_NVME_MI_DATA_STRUCTURE,
            request_func=lambda: self._sphinx.nvme_mi.get_controller_list(eid=self._eid),
            data_type=NVMeDataStructureType.CONTROLLER_LIST,
        )

        # Controller Information for each controller
        for ctrl_id in self._profile.metadata.controller_ids:
            self._capture_command(
                name=f"Controller {ctrl_id} Information",
                category=CommandCategory.DATA_STRUCTURE.value,
                opcode=NVMeMIOpcode.READ_NVME_MI_DATA_STRUCTURE,
                request_func=lambda cid=ctrl_id: self._sphinx.nvme_mi.read_data_structure(
                    NVMeDataStructureType.CONTROLLER_INFORMATION,
                    eid=self._eid,
                    controller_id=cid,
                ),
                request_data=[NVMeDataStructureType.CONTROLLER_INFORMATION, ctrl_id],
                data_type=NVMeDataStructureType.CONTROLLER_INFORMATION,
            )

        # Optionally Supported Commands
        self._capture_command(
            name="Optionally Supported Commands",
            category=CommandCategory.DATA_STRUCTURE.value,
            opcode=NVMeMIOpcode.READ_NVME_MI_DATA_STRUCTURE,
            request_func=lambda: self._sphinx.nvme_mi.read_data_structure(
                NVMeDataStructureType.OPTIONALLY_SUPPORTED_COMMANDS,
                eid=self._eid,
            ),
            data_type=NVMeDataStructureType.OPTIONALLY_SUPPORTED_COMMANDS,
        )

        # Management Endpoint Buffer Info
        self._capture_command(
            name="Management Endpoint Buffer Info",
            category=CommandCategory.DATA_STRUCTURE.value,
            opcode=NVMeMIOpcode.READ_NVME_MI_DATA_STRUCTURE,
            request_func=lambda: self._sphinx.nvme_mi.read_data_structure(
                NVMeDataStructureType.MANAGEMENT_ENDPOINT_BUFFER_INFO,
                eid=self._eid,
            ),
            data_type=NVMeDataStructureType.MANAGEMENT_ENDPOINT_BUFFER_INFO,
        )

    def _capture_configuration_commands(self) -> None:
        """Capture Configuration Get commands."""
        self._log("\n[Configuration Commands]")

        # Standard configuration identifiers
        config_ids = [
            (ConfigurationIdentifier.SMBUS_I2C_FREQUENCY, "SMBus/I2C Frequency"),
            (ConfigurationIdentifier.HEALTH_STATUS_CHANGE, "Health Status Change"),
            (ConfigurationIdentifier.MCTP_TRANSMISSION_UNIT, "MCTP MTU"),
        ]

        for config_id, name in config_ids:
            self._capture_command(
                name=f"Config Get: {name}",
                category=CommandCategory.CONFIGURATION.value,
                opcode=NVMeMIOpcode.CONFIGURATION_GET,
                request_func=lambda cid=config_id: self._sphinx.nvme_mi.configuration_get(
                    cid, eid=self._eid
                ),
                request_data=[config_id],
                config_id=config_id,
            )

    def _capture_vpd_commands(self) -> None:
        """Capture VPD Read commands."""
        self._log("\n[VPD Commands]")

        # Read VPD in chunks to capture full content
        offset = 0
        chunk_size = self._config.vpd_chunk_size

        while offset < self._config.vpd_max_offset:
            result = self._capture_command(
                name=f"VPD Read (offset={offset})",
                category=CommandCategory.VPD.value,
                opcode=NVMeMIOpcode.VPD_READ,
                request_func=lambda o=offset: self._sphinx.nvme_mi.vpd_read(
                    offset=o,
                    length=chunk_size,
                    eid=self._eid,
                ),
                request_data=[
                    offset & 0xFF,
                    (offset >> 8) & 0xFF,
                    chunk_size & 0xFF,
                    (chunk_size >> 8) & 0xFF,
                ],
            )

            # Stop if we get an error or empty response
            if result and result.success:
                vpd_len = result.decoded_fields.get("VPD Data Length", "0")
                try:
                    actual_len = int(vpd_len)
                    if actual_len < chunk_size:
                        # Got less than requested - end of VPD
                        break
                except (ValueError, TypeError):
                    break
            else:
                # VPD read failed - stop
                break

            offset += chunk_size

    def _capture_admin_tunneled_commands(self) -> None:
        """
        Capture Admin commands tunneled through MI Send/Receive.

        This requires MI Send/Receive support in the device.
        Falls back to firmware shortcuts if available.
        """
        self._log("\n[Admin Tunneled Commands]")

        # Check if MI Send/Receive is supported
        # For now, try using firmware shortcuts if available
        try:
            # Try firmware shortcuts for serial number
            sn_result = self._transport.get_serial_number(slot=self._slot)
            if sn_result.success:
                self._profile.metadata.serial_number = sn_result.serial_number
                self._log(f"  Serial Number (shortcut): {sn_result.serial_number}")

                # Capture the raw response for replay
                if sn_result.raw_packets:
                    cmd = CapturedCommand(
                        opcode=0xF0,  # Pseudo-opcode for shortcut
                        opcode_name="FIRMWARE_SHORTCUT_SN",
                        category=CommandCategory.ADMIN_TUNNELED.value,
                        request_data=[self._slot],
                        eid=self._eid,
                        success=True,
                        status_code=0,
                        status_name="SUCCESS",
                        response_raw=[b for pkt in sn_result.raw_packets for b in pkt],
                        response_payload=[],
                        latency_ms=0,
                        timestamp=datetime.now().isoformat(),
                        decoded_fields={"serial_number": sn_result.serial_number},
                    )
                    self._profile.add_command(cmd)
        except Exception as e:
            self._log(f"  Serial Number shortcut failed: {e}")

        # Note: Full MI Send/Receive implementation would go here
        # For now, we log that it would be captured
        self._log("  Note: Full MI Send/Receive tunneling not yet implemented")
        self._log("  Use firmware shortcuts for Identify/SMART data")

    def _log(self, message: str) -> None:
        """Log a message if verbose mode is enabled."""
        if self._config.verbose:
            print(message)

    def _progress(self, message: str) -> None:
        """Report progress."""
        if self._config.progress_callback:
            total = self._profile.metadata.total_commands if self._profile else 0
            self._config.progress_callback(message, total, total + 1)
        elif self._config.verbose:
            print(message)
