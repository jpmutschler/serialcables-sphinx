"""
Tests for mock transport and basic Sphinx functionality.

Run with: pytest tests/test_mock_transport.py -v
"""

import pytest

from serialcables_sphinx import NVMeMIOpcode, NVMeMIStatus, Sphinx
from serialcables_sphinx.transports.mock import MockDeviceState, MockTransport


class TestMockTransport:
    """Tests for MockTransport class."""

    def test_create_default(self):
        """Test creating mock with default state."""
        mock = MockTransport()
        assert mock.state is not None
        assert mock.state.temperature_kelvin == 318
        assert mock.state.ready is True

    def test_create_custom_state(self):
        """Test creating mock with custom state."""
        state = MockDeviceState(temperature_kelvin=350, available_spare=50)
        mock = MockTransport(state=state)
        assert mock.state.temperature_kelvin == 350
        assert mock.state.available_spare == 50

    def test_packet_recording(self):
        """Test that packets are recorded."""
        mock = MockTransport()
        sphinx = Sphinx(mock)

        sphinx.nvme_mi.health_status_poll(eid=1)

        assert len(mock.sent_packets) == 1
        assert mock.get_last_opcode() == NVMeMIOpcode.NVM_SUBSYSTEM_HEALTH_STATUS_POLL

    def test_reset(self):
        """Test reset clears tracking."""
        mock = MockTransport()
        sphinx = Sphinx(mock)

        sphinx.nvme_mi.health_status_poll(eid=1)
        assert len(mock.sent_packets) == 1

        mock.reset()
        assert len(mock.sent_packets) == 0

    def test_error_injection(self):
        """Test fail_next causes error."""
        mock = MockTransport()
        sphinx = Sphinx(mock)

        mock.inject_error("Test error")

        with pytest.raises(RuntimeError, match="Test error"):
            sphinx.nvme_mi.health_status_poll(eid=1)

        # Should work again after
        result = sphinx.nvme_mi.health_status_poll(eid=1)
        assert result.success


class TestHealthStatusPoll:
    """Tests for health status poll command."""

    def test_success_response(self):
        """Test successful health status poll."""
        mock = MockTransport()
        sphinx = Sphinx(mock)

        result = sphinx.nvme_mi.health_status_poll(eid=1)

        assert result.success
        assert result.status_code == NVMeMIStatus.SUCCESS
        assert result.opcode_value == NVMeMIOpcode.NVM_SUBSYSTEM_HEALTH_STATUS_POLL

    def test_temperature_decoding(self):
        """Test temperature is correctly decoded."""
        mock = MockTransport()
        mock.state.temperature_kelvin = 318  # 45°C
        sphinx = Sphinx(mock)

        result = sphinx.nvme_mi.health_status_poll(eid=1)

        temp_str = result["Composite Temperature"]
        assert "45°C" in temp_str
        assert "318 K" in temp_str

    def test_spare_threshold_warning(self):
        """Test spare below threshold detection."""
        mock = MockTransport()
        mock.state.available_spare = 5
        mock.state.spare_threshold = 10
        sphinx = Sphinx(mock)

        result = sphinx.nvme_mi.health_status_poll(eid=1)

        spare_field = result.get_field("Available Spare")
        assert spare_field is not None
        assert "Below threshold" in spare_field.description

    def test_ready_status(self):
        """Test ready status decoding."""
        mock = MockTransport()
        mock.state.ready = True
        sphinx = Sphinx(mock)

        result = sphinx.nvme_mi.health_status_poll(eid=1)
        assert result["Ready (RDY)"] is True

        mock.state.ready = False
        result = sphinx.nvme_mi.health_status_poll(eid=1)
        assert result["Ready (RDY)"] is False


class TestReadDataStructure:
    """Tests for Read NVMe-MI Data Structure command."""

    def test_subsystem_info(self):
        """Test reading subsystem information."""
        mock = MockTransport()
        mock.state.nvme_mi_major = 1
        mock.state.nvme_mi_minor = 2
        mock.state.num_ports = 2
        sphinx = Sphinx(mock)

        result = sphinx.nvme_mi.get_subsystem_info(eid=1)

        assert result.success
        assert result["NVMe-MI Version"] == "1.2"
        assert result["Number of Ports"] == 2

    def test_controller_list(self):
        """Test reading controller list."""
        mock = MockTransport()
        mock.state.controller_ids = [0, 1, 2]
        sphinx = Sphinx(mock)

        result = sphinx.nvme_mi.get_controller_list(eid=1)

        assert result.success
        assert result["Number of Controllers"] == 3
        assert result["Controller IDs"] == [0, 1, 2]

    def test_port_info(self):
        """Test reading port information."""
        mock = MockTransport()
        mock.state.port_type = 0x02  # SMBus/I2C
        mock.state.max_mctp_mtu = 64
        sphinx = Sphinx(mock)

        result = sphinx.nvme_mi.get_port_info(port_id=0, eid=1)

        assert result.success
        assert "SMBus" in result["Port Type"]
        assert result["Max MCTP Transmission Unit"] == 64


class TestControllerHealthStatus:
    """Tests for controller health status poll."""

    def test_valid_controller(self):
        """Test polling valid controller."""
        mock = MockTransport()
        mock.state.controller_ids = [0, 1]
        sphinx = Sphinx(mock)

        result = sphinx.nvme_mi.controller_health_status(controller_id=0, eid=1)

        assert result.success
        assert result["Controller ID"] == 0

    def test_invalid_controller(self):
        """Test polling non-existent controller."""
        mock = MockTransport()
        mock.state.controller_ids = [0]
        sphinx = Sphinx(mock)

        result = sphinx.nvme_mi.controller_health_status(controller_id=99, eid=1)

        assert not result.success
        assert result.status_code == NVMeMIStatus.INVALID_PARAMETER


class TestVPDRead:
    """Tests for VPD read command."""

    def test_read_vpd(self):
        """Test reading VPD data."""
        mock = MockTransport()
        mock.state.vpd_data = b"Test VPD Data 12345"
        sphinx = Sphinx(mock)

        result = sphinx.nvme_mi.vpd_read(offset=0, length=256, eid=1)

        assert result.success
        assert "Test VPD Data" in result["VPD Content"]


class TestOutputFormats:
    """Tests for response output formats."""

    def test_to_dict(self):
        """Test dictionary export."""
        mock = MockTransport()
        sphinx = Sphinx(mock)

        result = sphinx.nvme_mi.health_status_poll(eid=1)
        data = result.to_dict()

        assert "opcode" in data
        assert "status" in data
        assert "success" in data
        assert "fields" in data
        assert data["success"] is True

    def test_to_flat_dict(self):
        """Test flat dictionary export."""
        mock = MockTransport()
        sphinx = Sphinx(mock)

        result = sphinx.nvme_mi.health_status_poll(eid=1)
        flat = result.to_flat_dict()

        assert "success" in flat
        assert "Composite Temperature" in flat

    def test_pretty_print(self):
        """Test pretty print output."""
        mock = MockTransport()
        sphinx = Sphinx(mock)

        result = sphinx.nvme_mi.health_status_poll(eid=1)
        output = result.pretty_print()

        assert "NVMe-MI Response" in output
        assert "Status:" in output
        assert "Decoded Fields:" in output

    def test_summary(self):
        """Test one-line summary."""
        mock = MockTransport()
        sphinx = Sphinx(mock)

        result = sphinx.nvme_mi.health_status_poll(eid=1)
        summary = result.summary()

        assert "✓" in summary  # Success indicator
        assert "SUCCESS" in summary


class TestMCTPBuilder:
    """Tests for MCTP packet building."""

    def test_build_health_poll_packet_with_ic(self):
        """Test building health poll packet with integrity check (default)."""
        mock = MockTransport()
        sphinx = Sphinx(mock)

        # Use the high-level API which uses the new 14-byte format
        sphinx.nvme_mi.health_status_poll(eid=0)
        packet = mock.get_last_request()

        # Verify structure (with SMBus source addr at offset 3)
        # [0]=SMBus dest, [1]=Cmd code, [2]=Byte count, [3]=SMBus src
        # [4]=MCTP ver, [5]=Dest EID, [6]=Src EID, [7]=Flags/Tag
        # [8]=Msg type (0x84 with IC bit)
        # [9]=NMIMT/ROR, [10]=Reserved, [11]=Reserved, [12]=Opcode, [13+]=Data, [22]=Flags(0x80)
        # [23-26]=MIC, [27]=PEC
        assert packet[0] == 0x3A  # Default SMBus address
        assert packet[1] == 0x0F  # MCTP command code
        assert packet[3] == 0x21  # SMBus source address
        assert packet[5] == 0x00  # Dest EID = 0 for mux
        assert packet[8] == 0x84  # NVMe-MI message type with IC bit set
        assert packet[9] == 0x08  # NMIMT/ROR (MI Command per HYDRA)
        assert packet[10] == 0x00  # Reserved
        assert packet[11] == 0x00  # Reserved
        assert packet[12] == 0x01  # Health poll opcode (at byte 3 of NVMe-MI payload)
        assert packet[22] == 0x80  # Flags byte at end of 14-byte payload

    def test_build_packet_without_ic(self):
        """Test building packet without integrity check."""
        mock = MockTransport()
        sphinx = Sphinx(mock)

        # Build a 14-byte payload matching firmware format
        payload = bytes([0x08, 0x00, 0x00, 0x01]) + bytes(9) + bytes([0x80])  # 14 bytes
        packet = sphinx.mctp.build_nvme_mi_request(
            dest_eid=0,
            payload=payload,
            integrity_check=False,
        )

        assert packet[8] == 0x04  # NVMe-MI message type without IC bit

    def test_pec_calculation(self):
        """Test PEC is appended."""
        mock = MockTransport()
        sphinx = Sphinx(mock)

        # Build a 14-byte payload matching firmware format
        payload = bytes([0x08, 0x00, 0x00, 0x00]) + bytes(9) + bytes([0x80])  # 14 bytes
        packet = sphinx.mctp.build_nvme_mi_request(
            dest_eid=0,
            payload=payload,
            integrity_check=False,  # Simpler to verify without MIC
        )

        # Per DSP0237: byte_count includes bytes from SMBus src through PEC
        # byte_count = SMBus src (1) + MCTP header (4) + msg_type (1) + payload (14) + PEC (1) = 21
        byte_count = packet[2]
        assert byte_count == 1 + 4 + 1 + 14 + 1  # 21 bytes

        # Total packet = SMBus prefix (3) + SMBus src (1) + MCTP data (byte_count - 1 - 1 for src and PEC) + PEC (1)
        # Or simply: packet length = 3 + byte_count (since byte_count includes src through PEC)
        assert len(packet) == 3 + byte_count

    def test_mic_calculation(self):
        """Test MIC (CRC-32C) is appended when IC bit is set."""
        mock = MockTransport()
        sphinx = Sphinx(mock)

        # Build a 14-byte payload matching firmware format
        payload = bytes([0x08, 0x00, 0x00, 0x01]) + bytes(9) + bytes([0x80])  # 14 bytes
        packet = sphinx.mctp.build_nvme_mi_request(
            dest_eid=0,
            payload=payload,
            integrity_check=True,
        )

        # Per DSP0237: byte_count includes bytes from SMBus src through PEC
        # byte_count = SMBus src (1) + MCTP header (4) + msg_type (1) + payload (14) + MIC (4) + PEC (1) = 25
        byte_count = packet[2]
        assert byte_count == 1 + 4 + 1 + 14 + 4 + 1  # 25 bytes

        # Total packet = 3 + byte_count (since byte_count includes src through PEC)
        assert len(packet) == 3 + byte_count

    def test_firmware_format_packet_structure(self):
        """Test that packet structure matches HYDRA firmware format."""
        mock = MockTransport()
        sphinx = Sphinx(mock)

        # Use high-level API
        sphinx.nvme_mi.health_status_poll(eid=0)
        packet = mock.get_last_request()

        # Firmware packet format (28 bytes total):
        # 3a 0f 19 21 01 00 00 eb 84 08 00 00 01 00 00 00 00 00 00 00 00 00 80 aa ef 81 b4 48
        #
        # Breakdown:
        # [0] 3a = SMBus dest addr
        # [1] 0f = MCTP command code
        # [2] 19 = Byte count (25 per DSP0237: includes SMBus src through PEC)
        # [3] 21 = SMBus src addr
        # [4-7] = MCTP header (01 00 00 xx)
        # [8] 84 = Message type (NVMe-MI with IC bit)
        # [9-22] = NVMe-MI payload (14 bytes): 08 00 00 01 00 00 00 00 00 00 00 00 00 80
        # [23-26] = MIC (4 bytes)
        # [27] = PEC (1 byte)

        # Per DSP0237: byte_count = SMBus src (1) + MCTP header (4) + msg_type (1) + payload (14) + MIC (4) + PEC (1) = 25
        assert packet[2] == 25, f"Expected byte count 25, got {packet[2]}"

        # Verify total packet length = 3 + byte_count = 28 bytes
        assert len(packet) == 28, f"Expected 28 bytes, got {len(packet)}"

        # Verify NVMe-MI payload structure
        nvme_mi_payload = packet[9:23]  # 14 bytes
        assert len(nvme_mi_payload) == 14
        assert nvme_mi_payload[0] == 0x08  # NMIMT/ROR
        assert nvme_mi_payload[1] == 0x00  # Reserved
        assert nvme_mi_payload[2] == 0x00  # Reserved
        assert nvme_mi_payload[3] == 0x01  # Opcode (health status poll)
        assert nvme_mi_payload[13] == 0x80  # Flags byte


class TestDiscovery:
    """Tests for subsystem discovery."""

    def test_discover_subsystem(self):
        """Test full subsystem discovery."""
        mock = MockTransport()
        mock.state.controller_ids = [0, 1]
        sphinx = Sphinx(mock)

        discovery = sphinx.nvme_mi.discover_subsystem(eid=1)

        assert "subsystem" in discovery
        assert "health" in discovery
        assert "controllers" in discovery

        assert discovery["subsystem"] is not None
        assert discovery["health"] is not None
        assert len(discovery["controllers"]) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
