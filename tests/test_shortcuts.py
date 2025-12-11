"""
Tests for MCTP firmware shortcuts module.
"""

from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock

import pytest

from serialcables_sphinx.shortcuts import (
    HealthStatusResult,
    MCTPShortcutCommand,
    MCTPShortcuts,
    SerialNumberResult,
)


# Mock HYDRA response dataclasses
@dataclass
class MockNVMeSerialNumber:
    slot: int
    serial_number: str
    success: bool
    raw_packets: list[list[int]]
    error: Optional[str] = None


@dataclass
class MockNVMeHealthStatus:
    slot: int
    success: bool
    raw_packets: list[list[int]]
    composite_temperature: Optional[int] = None
    composite_temperature_celsius: Optional[float] = None
    available_spare: Optional[int] = None
    available_spare_threshold: Optional[int] = None
    percentage_used: Optional[int] = None
    critical_warning: Optional[int] = None
    error: Optional[str] = None


class TestSerialNumberResult:
    """Tests for SerialNumberResult dataclass."""

    def test_success_result(self):
        result = SerialNumberResult(
            slot=1,
            serial_number="ABC123",
            success=True,
        )
        assert result.success
        assert result.serial_number == "ABC123"
        assert "ABC123" in str(result)

    def test_error_result(self):
        result = SerialNumberResult(
            slot=2,
            serial_number="",
            success=False,
            error="No response",
        )
        assert not result.success
        assert "Error" in str(result)


class TestHealthStatusResult:
    """Tests for HealthStatusResult dataclass."""

    def test_healthy_drive(self):
        result = HealthStatusResult(
            slot=1,
            success=True,
            temperature_kelvin=318,
            temperature_celsius=45.0,
            available_spare=95,
            spare_threshold=10,
            percentage_used=5,
            critical_warning=0,
        )

        assert result.is_healthy
        assert "45°C" in result.summary()
        assert "Spare:95%" in result.summary()

    def test_unhealthy_spare_low(self):
        result = HealthStatusResult(
            slot=1,
            success=True,
            available_spare=5,
            spare_threshold=10,
            critical_warning=0,
        )

        assert not result.is_healthy  # Spare below threshold

    def test_unhealthy_warning(self):
        result = HealthStatusResult(
            slot=1,
            success=True,
            available_spare=95,
            spare_threshold=10,
            critical_warning=0x01,  # Warning bit set
        )

        assert not result.is_healthy
        assert "Warning" in result.summary()

    def test_error_result(self):
        result = HealthStatusResult(
            slot=3,
            success=False,
            error="Command not supported",
        )

        assert not result.is_healthy
        assert "Error" in result.summary()

    def test_summary_format(self):
        result = HealthStatusResult(
            slot=1,
            success=True,
            temperature_celsius=50.0,
            available_spare=80,
            percentage_used=20,
        )

        summary = result.summary()
        assert "Slot 1" in summary
        assert "50°C" in summary
        assert "Spare:80%" in summary
        assert "Used:20%" in summary


class TestMCTPShortcutCommand:
    """Tests for MCTPShortcutCommand enum."""

    def test_serial_number_command(self):
        assert MCTPShortcutCommand.SERIAL_NUMBER.value == "sn"

    def test_health_status_command(self):
        assert MCTPShortcutCommand.HEALTH_STATUS.value == "health"


class TestMCTPShortcuts:
    """Tests for MCTPShortcuts class."""

    @pytest.fixture
    def mock_jbof(self):
        """Create mock JBOFController."""
        jbof = MagicMock()
        return jbof

    @pytest.fixture
    def shortcuts(self, mock_jbof):
        """Create MCTPShortcuts with mock JBOF."""
        return MCTPShortcuts(mock_jbof, timeout=2.0, decode_responses=False)

    def test_get_serial_number_success(self, shortcuts, mock_jbof):
        mock_jbof.mctp_get_serial_number.return_value = MockNVMeSerialNumber(
            slot=1,
            serial_number="TEST_SERIAL_123",
            success=True,
            raw_packets=[[0x20, 0x0F, 0x10]],
        )

        result = shortcuts.get_serial_number(slot=1)

        assert result.success
        assert result.serial_number == "TEST_SERIAL_123"
        assert result.slot == 1
        mock_jbof.mctp_get_serial_number.assert_called_once()

    def test_get_serial_number_error(self, shortcuts, mock_jbof):
        mock_jbof.mctp_get_serial_number.return_value = MockNVMeSerialNumber(
            slot=1,
            serial_number="",
            success=False,
            raw_packets=[],
            error="No response",
        )

        result = shortcuts.get_serial_number(slot=1)

        assert not result.success
        assert result.error == "No response"

    def test_get_health_status_success(self, shortcuts, mock_jbof):
        mock_jbof.mctp_get_health_status.return_value = MockNVMeHealthStatus(
            slot=2,
            success=True,
            raw_packets=[[0x20, 0x0F, 0x10]],
            composite_temperature=320,
            composite_temperature_celsius=47.0,
            available_spare=90,
            available_spare_threshold=10,
            percentage_used=8,
            critical_warning=0,
        )

        result = shortcuts.get_health_status(slot=2)

        assert result.success
        assert result.temperature_celsius == 47.0
        assert result.available_spare == 90
        assert result.is_healthy

    def test_get_health_status_unsupported(self, shortcuts, mock_jbof):
        mock_jbof.mctp_get_health_status.return_value = MockNVMeHealthStatus(
            slot=1,
            success=False,
            raw_packets=[],
            error="Unsupported command",
        )

        result = shortcuts.get_health_status(slot=1)

        assert not result.success
        assert "Unsupported" in result.error

    def test_scan_all_slots(self, shortcuts, mock_jbof):
        # Simulate slots 1-3 have drives, rest empty
        def mock_serial(slot, timeout=None):
            if slot <= 3:
                return MockNVMeSerialNumber(
                    slot=slot,
                    serial_number=f"DRIVE_{slot}",
                    success=True,
                    raw_packets=[],
                )
            return MockNVMeSerialNumber(
                slot=slot,
                serial_number="",
                success=False,
                raw_packets=[],
                error="No response",
            )

        mock_jbof.mctp_get_serial_number.side_effect = mock_serial

        results = shortcuts.scan_all_slots()

        assert len(results) == 8
        assert sum(1 for r in results if r.success) == 3
        assert results[0].serial_number == "DRIVE_1"

    def test_custom_timeout(self, mock_jbof):
        shortcuts = MCTPShortcuts(mock_jbof, timeout=5.0)

        mock_jbof.mctp_get_serial_number.return_value = MockNVMeSerialNumber(
            slot=1,
            serial_number="X",
            success=True,
            raw_packets=[],
        )

        shortcuts.get_serial_number(slot=1)

        # Verify timeout was passed
        call_kwargs = mock_jbof.mctp_get_serial_number.call_args
        assert call_kwargs[1].get("timeout") == 5.0

    def test_timeout_override(self, shortcuts, mock_jbof):
        mock_jbof.mctp_get_serial_number.return_value = MockNVMeSerialNumber(
            slot=1,
            serial_number="X",
            success=True,
            raw_packets=[],
        )

        shortcuts.get_serial_number(slot=1, timeout=10.0)

        call_kwargs = mock_jbof.mctp_get_serial_number.call_args
        assert call_kwargs[1].get("timeout") == 10.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
