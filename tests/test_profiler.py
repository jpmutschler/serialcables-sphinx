"""
Tests for device profiler module.

Tests cover:
- DeviceProfile creation and serialization
- CapturedCommand structure
- Profile loading and saving
- MockTransport integration with profiles
"""

import os
import tempfile
from datetime import datetime

import pytest

from serialcables_sphinx.profiler.loader import ProfileLoader
from serialcables_sphinx.profiler.profile import (
    CapturedCommand,
    CommandCategory,
    DeviceProfile,
    ProfileMetadata,
)


class TestCapturedCommand:
    """Tests for CapturedCommand dataclass."""

    def test_create_success_command(self):
        cmd = CapturedCommand(
            opcode=0x01,
            opcode_name="NVM_SUBSYSTEM_HEALTH_STATUS_POLL",
            category=CommandCategory.HEALTH.value,
            request_data=[],
            eid=1,
            success=True,
            status_code=0x00,
            status_name="SUCCESS",
            response_raw=[0x02, 0x00, 0x00, 0x00, 0x01, 0x00, 0x3E, 0x01],
            response_payload=[0x01, 0x00, 0x3E, 0x01],
            latency_ms=5.2,
            timestamp=datetime.now().isoformat(),
            decoded_fields={"Composite Temperature": "45°C (318 K)"},
        )

        assert cmd.success
        assert cmd.opcode == 0x01
        assert cmd.latency_ms == 5.2

    def test_create_error_command(self):
        cmd = CapturedCommand(
            opcode=0x05,
            opcode_name="VPD_READ",
            category=CommandCategory.VPD.value,
            request_data=[0x00, 0x00, 0x00, 0x01],
            eid=1,
            success=False,
            status_code=0x03,
            status_name="INVALID_PARAMETER",
            response_raw=[0x02, 0x03, 0x00, 0x00],
            response_payload=[],
            latency_ms=2.1,
            timestamp=datetime.now().isoformat(),
            error="VPD not supported",
        )

        assert not cmd.success
        assert cmd.status_code == 0x03

    def test_to_dict(self):
        cmd = CapturedCommand(
            opcode=0x01,
            opcode_name="TEST",
            category="health",
            request_data=[],
            eid=1,
            success=True,
            status_code=0,
            status_name="SUCCESS",
            response_raw=[1, 2, 3],
            response_payload=[1, 2, 3],
            latency_ms=1.0,
            timestamp="2024-01-01T00:00:00",
        )

        d = cmd.to_dict()
        assert d["opcode"] == 0x01
        assert d["success"]
        assert d["response_raw"] == [1, 2, 3]

    def test_from_dict(self):
        d = {
            "opcode": 0x02,
            "opcode_name": "TEST",
            "category": "health",
            "request_data": [1, 2],
            "eid": 1,
            "success": True,
            "status_code": 0,
            "status_name": "SUCCESS",
            "response_raw": [4, 5, 6],
            "response_payload": [4, 5, 6],
            "latency_ms": 2.5,
            "timestamp": "2024-01-01",
            "decoded_fields": {},
            "data_type": None,
            "data_type_name": None,
            "config_id": None,
            "config_id_name": None,
            "admin_opcode": None,
            "admin_opcode_name": None,
            "error": None,
        }

        cmd = CapturedCommand.from_dict(d)
        assert cmd.opcode == 0x02
        assert cmd.request_data == [1, 2]


class TestProfileMetadata:
    """Tests for ProfileMetadata."""

    def test_create_metadata(self):
        meta = ProfileMetadata(
            capture_date="2024-01-01T12:00:00",
            capture_duration_seconds=30.5,
            sphinx_version="0.1.0",
            hydra_version="1.2.1",
            serial_number="ABC123",
            model_number="Test Device",
        )

        assert meta.serial_number == "ABC123"
        assert meta.capture_duration_seconds == 30.5

    def test_to_dict(self):
        meta = ProfileMetadata(
            capture_date="2024-01-01",
            capture_duration_seconds=10.0,
            sphinx_version="0.1.0",
            hydra_version="1.2.0",
        )

        d = meta.to_dict()
        assert "capture_date" in d
        assert "sphinx_version" in d


class TestDeviceProfile:
    """Tests for DeviceProfile."""

    @pytest.fixture
    def sample_profile(self):
        """Create a sample profile for testing."""
        profile = DeviceProfile(profile_name="test_profile")
        profile.metadata = ProfileMetadata(
            capture_date="2024-01-01T12:00:00",
            capture_duration_seconds=60.0,
            sphinx_version="0.1.0",
            hydra_version="1.2.1",
            serial_number="TEST123",
            model_number="Test NVMe Device",
        )

        # Add health command
        health_cmd = CapturedCommand(
            opcode=0x01,
            opcode_name="NVM_SUBSYSTEM_HEALTH_STATUS_POLL",
            category=CommandCategory.HEALTH.value,
            request_data=[],
            eid=1,
            success=True,
            status_code=0x00,
            status_name="SUCCESS",
            response_raw=[0x02, 0x00, 0x00, 0x00, 0x01, 0x00, 0x3E, 0x01, 0x05, 0x0A, 0x64],
            response_payload=[0x01, 0x00, 0x3E, 0x01, 0x05, 0x0A, 0x64],
            latency_ms=5.0,
            timestamp="2024-01-01T12:00:01",
            decoded_fields={
                "Composite Temperature": "45°C (318 K)",
                "Available Spare": "100%",
            },
        )
        profile.add_command(health_cmd)

        # Add data structure command
        ds_cmd = CapturedCommand(
            opcode=0x00,
            opcode_name="READ_NVME_MI_DATA_STRUCTURE",
            category=CommandCategory.DATA_STRUCTURE.value,
            request_data=[0x00, 0x00, 0x00, 0x00],
            eid=1,
            success=True,
            status_code=0x00,
            status_name="SUCCESS",
            response_raw=[0x02, 0x00, 0x00, 0x00, 0x01, 0x01, 0x02],
            response_payload=[0x01, 0x01, 0x02],
            latency_ms=3.0,
            timestamp="2024-01-01T12:00:02",
            data_type=0x00,
            data_type_name="NVM_SUBSYSTEM_INFORMATION",
            decoded_fields={
                "Number of Ports": "1",
                "NVMe-MI Major Version": "1",
                "NVMe-MI Minor Version": "2",
            },
        )
        profile.add_command(ds_cmd)

        return profile

    def test_add_command(self, sample_profile):
        assert len(sample_profile.health_commands) == 1
        assert len(sample_profile.data_structure_commands) == 1

    def test_get_all_commands(self, sample_profile):
        all_cmds = sample_profile.get_all_commands()
        assert len(all_cmds) == 2

    def test_response_table_populated(self, sample_profile):
        assert "0x01" in sample_profile.response_table
        assert "0x00" in sample_profile.response_table

    def test_to_dict(self, sample_profile):
        d = sample_profile.to_dict()
        assert d["profile_name"] == "test_profile"
        assert len(d["health_commands"]) == 1

    def test_from_dict(self, sample_profile):
        d = sample_profile.to_dict()
        loaded = DeviceProfile.from_dict(d)

        assert loaded.profile_name == "test_profile"
        assert len(loaded.health_commands) == 1
        assert len(loaded.data_structure_commands) == 1

    def test_save_and_load(self, sample_profile):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            filepath = f.name

        try:
            sample_profile.save(filepath)
            loaded = DeviceProfile.load(filepath)

            assert loaded.profile_name == sample_profile.profile_name
            assert len(loaded.get_all_commands()) == len(sample_profile.get_all_commands())
            assert loaded.verify_checksum()
        finally:
            os.unlink(filepath)

    def test_checksum(self, sample_profile):
        checksum1 = sample_profile.calculate_checksum()

        # Should be consistent
        checksum2 = sample_profile.calculate_checksum()
        assert checksum1 == checksum2

        # Should change if content changes
        sample_profile.profile_name = "modified"
        checksum3 = sample_profile.calculate_checksum()
        assert checksum1 != checksum3

    def test_summary(self, sample_profile):
        summary = sample_profile.summary()
        assert "test_profile" in summary
        assert "Test NVMe Device" in summary


class TestProfileLoader:
    """Tests for ProfileLoader."""

    @pytest.fixture
    def sample_profile(self):
        """Create sample profile."""
        profile = DeviceProfile(profile_name="loader_test")
        profile.metadata = ProfileMetadata(
            capture_date="2024-01-01",
            capture_duration_seconds=30.0,
            sphinx_version="0.1.0",
            hydra_version="1.2.0",
            avg_latency_ms=5.0,
        )

        # Add health command with full response data
        cmd = CapturedCommand(
            opcode=0x01,
            opcode_name="NVM_SUBSYSTEM_HEALTH_STATUS_POLL",
            category=CommandCategory.HEALTH.value,
            request_data=[],
            eid=1,
            success=True,
            status_code=0x00,
            status_name="SUCCESS",
            response_raw=[0x02, 0x00, 0x00, 0x00, 0x01, 0x00, 0x3E, 0x01, 0x05, 0x0A, 0x64],
            response_payload=[0x01, 0x00, 0x3E, 0x01, 0x05, 0x0A, 0x64],
            latency_ms=5.0,
            timestamp="2024-01-01",
            decoded_fields={
                "Composite Temperature": "45°C (318 K)",
                "Available Spare": "100%",
                "Available Spare Threshold": "10%",
                "Drive Life Used": "5%",
                "Ready (RDY)": "True",
            },
        )
        profile.add_command(cmd)

        return profile

    def test_create_mock_from_profile(self, sample_profile):
        mock = ProfileLoader.create_mock(sample_profile)

        assert mock is not None
        assert hasattr(mock, "_loaded_profile")

    def test_profile_state_extraction(self, sample_profile):
        mock = ProfileLoader.create_mock(sample_profile)

        # State should be populated from profile
        # Note: depends on successful parsing of decoded_fields
        assert mock.state is not None

    def test_mock_with_sphinx(self, sample_profile):
        from serialcables_sphinx import Sphinx

        mock = ProfileLoader.create_mock(sample_profile)
        sphinx = Sphinx(mock)

        # Should be able to query the mock
        result = sphinx.nvme_mi.health_status_poll(eid=1)

        # Should get a response (either from profile or default mock)
        assert result is not None


class TestAdminTunneling:
    """Tests for admin command tunneling structures."""

    def test_mi_send_identify_controller(self):
        from serialcables_sphinx.nvme_mi.admin_tunneling import AdminOpcode, MISendRequest

        req = MISendRequest.identify_controller(controller_id=0)

        assert req.admin_opcode == AdminOpcode.IDENTIFY
        assert req.controller_id == 0

        packed = req.pack()
        assert len(packed) >= 36  # 9 DWORDs minimum

    def test_mi_send_get_smart_log(self):
        from serialcables_sphinx.nvme_mi.admin_tunneling import AdminOpcode, MISendRequest

        req = MISendRequest.get_smart_log(controller_id=0)

        assert req.admin_opcode == AdminOpcode.GET_LOG_PAGE

        packed = req.pack()
        assert len(packed) >= 36

    def test_mi_send_get_features(self):
        from serialcables_sphinx.nvme_mi.admin_tunneling import (
            AdminOpcode,
            FeatureIdentifier,
            MISendRequest,
        )

        req = MISendRequest.get_features(
            feature_id=FeatureIdentifier.TEMPERATURE_THRESHOLD,
            controller_id=0,
        )

        assert req.admin_opcode == AdminOpcode.GET_FEATURES

    def test_admin_opcodes(self):
        from serialcables_sphinx.nvme_mi.admin_tunneling import AdminOpcode

        assert AdminOpcode.IDENTIFY == 0x06
        assert AdminOpcode.GET_LOG_PAGE == 0x02
        assert AdminOpcode.GET_FEATURES == 0x0A
        assert AdminOpcode.SET_FEATURES == 0x09

    def test_identify_cns_values(self):
        from serialcables_sphinx.nvme_mi.admin_tunneling import IdentifyCNS

        assert IdentifyCNS.NAMESPACE == 0x00
        assert IdentifyCNS.CONTROLLER == 0x01
        assert IdentifyCNS.ACTIVE_NS_LIST == 0x02

    def test_log_page_identifiers(self):
        from serialcables_sphinx.nvme_mi.admin_tunneling import LogPageIdentifier

        assert LogPageIdentifier.ERROR_INFO == 0x01
        assert LogPageIdentifier.SMART_HEALTH == 0x02
        assert LogPageIdentifier.FIRMWARE_SLOT == 0x03


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
