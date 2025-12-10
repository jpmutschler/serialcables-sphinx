"""
Profile loader for MockTransport integration.

Loads captured device profiles and configures MockTransport
to replay the captured responses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from serialcables_sphinx.profiler.profile import CapturedCommand, DeviceProfile

if TYPE_CHECKING:
    from serialcables_sphinx.transports.mock import MockDeviceState, MockTransport


class ProfileLoader:
    """
    Loads device profiles into MockTransport for replay.

    This allows testing against captured real device behavior
    without needing the actual hardware.

    Example:
        from serialcables_sphinx.transports.mock import MockTransport
        from serialcables_sphinx.profiler import ProfileLoader, DeviceProfile

        # Load profile
        profile = DeviceProfile.load("samsung_990_pro.json")

        # Create mock from profile
        mock = ProfileLoader.create_mock(profile)

        # Use mock normally
        sphinx = Sphinx(mock)
        result = sphinx.nvme_mi.health_status_poll(eid=1)
    """

    @classmethod
    def create_mock(
        cls,
        profile: DeviceProfile,
        strict: bool = False,
    ) -> MockTransport:
        """
        Create a MockTransport configured with profile data.

        Args:
            profile: Device profile to use
            strict: If True, return errors for uncaptured commands

        Returns:
            Configured MockTransport
        """
        from serialcables_sphinx.transports.mock import MockTransport

        # Create mock with profile-based state
        state = cls._profile_to_state(profile)
        mock = MockTransport(state=state)

        # Install profile-based response handlers
        cls._install_handlers(mock, profile, strict)

        # Store profile reference
        mock._loaded_profile = profile

        return mock

    @classmethod
    def _profile_to_state(cls, profile: DeviceProfile) -> MockDeviceState:
        """
        Convert profile to MockDeviceState.

        Extracts values from captured commands to populate state.
        """
        from serialcables_sphinx.transports.mock import MockDeviceState

        state = MockDeviceState()

        # Extract from health commands
        for cmd in profile.health_commands:
            if cmd.success and cmd.decoded_fields:
                cls._extract_health_fields(state, cmd.decoded_fields)

        # Extract from subsystem info
        for cmd in profile.data_structure_commands:
            if cmd.success and cmd.decoded_fields:
                if cmd.data_type == 0x00:  # NVM_SUBSYSTEM_INFORMATION
                    cls._extract_subsystem_fields(state, cmd.decoded_fields)
                elif cmd.data_type == 0x02:  # CONTROLLER_LIST
                    cls._extract_controller_list(state, cmd.decoded_fields)

        # Extract VPD
        cls._extract_vpd(state, profile.vpd_commands)

        # Set timing based on profile
        if profile.metadata.avg_latency_ms > 0:
            state.response_delay_ms = profile.metadata.avg_latency_ms

        return state

    @classmethod
    def _extract_health_fields(cls, state: MockDeviceState, fields: dict[str, str]) -> None:
        """Extract health fields from decoded data."""
        # Temperature
        temp_str = fields.get("Composite Temperature", "")
        if "K" in temp_str:
            try:
                # Parse "45°C (318 K)" format
                k_idx = temp_str.find("K")
                paren_idx = temp_str.rfind("(")
                if paren_idx >= 0:
                    kelvin = int(temp_str[paren_idx + 1 : k_idx].strip())
                    state.temperature_kelvin = kelvin
            except (ValueError, IndexError):
                pass

        # Available spare
        spare_str = fields.get("Available Spare", "")
        if "%" in spare_str:
            try:
                state.available_spare = int(spare_str.replace("%", "").strip())
            except ValueError:
                pass

        # Spare threshold
        thresh_str = fields.get("Available Spare Threshold", "")
        if "%" in thresh_str:
            try:
                state.spare_threshold = int(thresh_str.replace("%", "").strip())
            except ValueError:
                pass

        # Life used
        life_str = fields.get("Drive Life Used", "")
        if "%" in life_str:
            try:
                state.life_used = int(life_str.replace("%", "").strip())
            except ValueError:
                pass

        # Critical warning
        cw_str = fields.get("Critical Warning", "")
        if "0x" in cw_str:
            try:
                state.critical_warning = int(cw_str.split("0x")[1].split()[0], 16)
            except (ValueError, IndexError):
                pass

        # Ready status
        rdy_str = fields.get("Ready (RDY)", "")
        state.ready = rdy_str.lower() == "true"

    @classmethod
    def _extract_subsystem_fields(cls, state: MockDeviceState, fields: dict[str, str]) -> None:
        """Extract subsystem info fields."""
        try:
            state.num_ports = int(fields.get("Number of Ports", "1"))
        except ValueError:
            pass

        try:
            state.nvme_mi_major = int(fields.get("NVMe-MI Major Version", "1"))
            state.nvme_mi_minor = int(fields.get("NVMe-MI Minor Version", "2"))
        except ValueError:
            pass

    @classmethod
    def _extract_controller_list(cls, state: MockDeviceState, fields: dict[str, str]) -> None:
        """Extract controller list."""
        ctrl_str = fields.get("Controller IDs", "[]")
        try:
            # Parse list string like "[0, 1]"
            ctrl_str = ctrl_str.strip("[]")
            if ctrl_str:
                state.controller_ids = [int(x.strip()) for x in ctrl_str.split(",")]
        except ValueError:
            pass

    @classmethod
    def _extract_vpd(cls, state: MockDeviceState, vpd_commands: list[CapturedCommand]) -> None:
        """Extract VPD data from captured commands."""
        vpd_data = bytearray()

        # Sort by offset (from request_data)
        sorted_cmds = sorted(
            [c for c in vpd_commands if c.success],
            key=lambda c: (
                (c.request_data[0] | (c.request_data[1] << 8)) if len(c.request_data) >= 2 else 0
            ),
        )

        for cmd in sorted_cmds:
            if cmd.response_payload and len(cmd.response_payload) > 2:
                # VPD response: [Length (2)][Data...]
                vpd_len = cmd.response_payload[0] | (cmd.response_payload[1] << 8)
                vpd_chunk = bytes(cmd.response_payload[2 : 2 + vpd_len])

                # Get offset from request
                if len(cmd.request_data) >= 2:
                    offset = cmd.request_data[0] | (cmd.request_data[1] << 8)
                    # Extend vpd_data if needed
                    while len(vpd_data) < offset + len(vpd_chunk):
                        vpd_data.append(0)
                    # Insert chunk
                    vpd_data[offset : offset + len(vpd_chunk)] = vpd_chunk

        if vpd_data:
            state.vpd_data = bytes(vpd_data)

    @classmethod
    def _install_handlers(
        cls,
        mock: MockTransport,
        profile: DeviceProfile,
        strict: bool,
    ) -> None:
        """
        Install custom handlers for profile-based responses.

        This replaces the default MockTransport handlers with ones
        that return the exact captured responses.
        """
        # Create lookup by opcode and parameters
        response_cache: dict[str, bytes] = {}

        for cmd in profile.get_all_commands():
            if cmd.success and cmd.response_raw:
                # Build cache key
                key = cls._make_cache_key(cmd)
                response_cache[key] = bytes(cmd.response_raw)

        # Install generic handler that uses cache
        def profile_handler(request_data: bytes, dest_eid: int) -> bytes:
            # Try to find matching response
            opcode = request_data[0] if request_data else 0

            # Build key for lookup
            key = f"{opcode:02X}_{dest_eid}_{request_data.hex()}"

            if key in response_cache:
                return response_cache[key]

            # Try opcode-only match
            for cached_key, response in response_cache.items():
                if cached_key.startswith(f"{opcode:02X}_"):
                    return response

            if strict:
                # Return error for uncaptured command
                from serialcables_sphinx.nvme_mi.status import NVMeMIStatus

                return bytes([0x02, NVMeMIStatus.INVALID_OPCODE, 0x00, 0x00])

            # Fall through to default handler
            return None

        # Store for use in custom handler
        mock._profile_cache = response_cache
        mock._profile_handler = profile_handler

    @classmethod
    def _make_cache_key(cls, cmd: CapturedCommand) -> str:
        """Create cache key for command lookup."""
        parts = [
            f"{cmd.opcode:02X}",
            str(cmd.eid),
        ]

        if cmd.data_type is not None:
            parts.append(f"dt{cmd.data_type}")
        if cmd.config_id is not None:
            parts.append(f"cfg{cmd.config_id}")
        if cmd.request_data:
            parts.append(bytes(cmd.request_data).hex())

        return "_".join(parts)


def load_profile_to_mock(filepath: str, strict: bool = False) -> MockTransport:
    """
    Convenience function to load a profile file into MockTransport.

    Args:
        filepath: Path to profile JSON file
        strict: If True, return errors for uncaptured commands

    Returns:
        Configured MockTransport

    Example:
        mock = load_profile_to_mock("my_device.json")
        sphinx = Sphinx(mock)
    """
    profile = DeviceProfile.load(filepath)
    return ProfileLoader.create_mock(profile, strict=strict)
