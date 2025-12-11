"""
Tests for MCTP message fragmentation and reassembly.

Tests cover:
- Fragmentation detection and calculation
- Fragment building with proper SOM/EOM/sequence
- Reassembly of multi-fragment messages
- Timing and configuration
"""

import pytest

from serialcables_sphinx import Sphinx
from serialcables_sphinx.mctp import (
    FragmentationConfig,
    FragmentationConstants,
    FragmentedMessage,
    MCTPBuilder,
    MessageReassembler,
    PacketSequence,
)
from serialcables_sphinx.transports.mock import MockTransport


class TestFragmentationConstants:
    """Tests for hardware limit constants."""

    def test_tx_limit(self):
        assert FragmentationConstants.MAX_TX_PACKET_SIZE == 128

    def test_rx_limit(self):
        assert FragmentationConstants.MAX_RX_PACKET_SIZE == 256

    def test_overhead_calculation(self):
        # 3 SMBus + 4 MCTP + 1 PEC = 8
        assert FragmentationConstants.PACKET_OVERHEAD == 8

    def test_max_payload_calculation(self):
        # 128 - 8 = 120
        assert FragmentationConstants.MAX_TX_PAYLOAD == 120
        # 256 - 8 = 248
        assert FragmentationConstants.MAX_RX_PAYLOAD == 248


class TestPacketSequence:
    """Tests for packet sequence management."""

    def test_initial_value(self):
        seq = PacketSequence()
        assert seq.current() == 0

    def test_increment(self):
        seq = PacketSequence()
        assert seq.next() == 0
        assert seq.next() == 1
        assert seq.next() == 2
        assert seq.next() == 3

    def test_wrap_at_4(self):
        seq = PacketSequence()
        for _ in range(4):
            seq.next()
        assert seq.current() == 0  # Wrapped
        assert seq.next() == 0
        assert seq.next() == 1

    def test_reset(self):
        seq = PacketSequence()
        seq.next()
        seq.next()
        seq.reset()
        assert seq.current() == 0

    def test_expect_next(self):
        seq = PacketSequence()
        assert seq.expect_next(0)
        assert seq.expect_next(1)
        assert not seq.expect_next(3)  # Out of order
        assert seq.expect_next(2)  # Still expecting 2


class TestFragmentationDetection:
    """Tests for detecting when fragmentation is needed."""

    def test_small_payload_no_fragmentation(self):
        builder = MCTPBuilder()
        payload = b"\x01\x00\x00\x00"  # 4 bytes
        assert not builder.needs_fragmentation(payload)

    def test_max_single_packet(self):
        builder = MCTPBuilder()
        # Max payload = 120, minus 1 for msg_type = 119 bytes of data
        payload = bytes(119)
        assert not builder.needs_fragmentation(payload)

    def test_just_over_limit(self):
        builder = MCTPBuilder()
        payload = bytes(120)  # +1 for msg_type = 121 > 120
        assert builder.needs_fragmentation(payload)

    def test_large_payload(self):
        builder = MCTPBuilder()
        payload = bytes(512)
        assert builder.needs_fragmentation(payload)


class TestFragmentCount:
    """Tests for fragment count calculation."""

    def test_single_fragment(self):
        builder = MCTPBuilder()
        payload = bytes(50)
        assert builder.calculate_fragment_count(payload) == 1

    def test_two_fragments(self):
        builder = MCTPBuilder()
        # 120 bytes per fragment, need 121-240 for 2 fragments
        payload = bytes(150)
        assert builder.calculate_fragment_count(payload) == 2

    def test_five_fragments(self):
        builder = MCTPBuilder()
        # 512 bytes = 5 fragments (120*4=480, plus remainder)
        payload = bytes(512)
        count = builder.calculate_fragment_count(payload)
        assert count == 5


class TestBuildFragmented:
    """Tests for building fragmented messages."""

    def test_single_fragment_message(self):
        builder = MCTPBuilder()
        payload = b"\x01\x00\x00\x00"

        result = builder.build_fragmented(
            dest_eid=1,
            msg_type=0x04,
            payload=payload,
        )

        assert isinstance(result, FragmentedMessage)
        assert result.fragment_count == 1
        assert not result.is_fragmented
        assert result.fragments[0].is_first
        assert result.fragments[0].is_last

    def test_multi_fragment_message(self):
        builder = MCTPBuilder()
        payload = bytes(300)  # Will need 3 fragments

        result = builder.build_fragmented(
            dest_eid=1,
            msg_type=0x04,
            payload=payload,
        )

        assert result.fragment_count == 3
        assert result.is_fragmented

        # Check first fragment
        assert result.fragments[0].is_first
        assert not result.fragments[0].is_last
        assert result.fragments[0].sequence == 0

        # Check middle fragment
        assert not result.fragments[1].is_first
        assert not result.fragments[1].is_last
        assert result.fragments[1].sequence == 1

        # Check last fragment
        assert not result.fragments[2].is_first
        assert result.fragments[2].is_last
        assert result.fragments[2].sequence == 2

    def test_fragment_packet_sizes(self):
        builder = MCTPBuilder()
        payload = bytes(300)

        result = builder.build_fragmented(
            dest_eid=1,
            msg_type=0x04,
            payload=payload,
        )

        # All fragments except last should be max size (128)
        for frag in result.fragments[:-1]:
            assert len(frag.data) == FragmentationConstants.MAX_TX_PACKET_SIZE

        # Last fragment should be smaller
        assert len(result.fragments[-1].data) < FragmentationConstants.MAX_TX_PACKET_SIZE

    def test_message_tag_preserved(self):
        builder = MCTPBuilder()
        builder._msg_tag = 5
        payload = bytes(300)

        result = builder.build_fragmented(
            dest_eid=1,
            msg_type=0x04,
            payload=payload,
        )

        assert result.message_tag == 5

        # All fragments should have same tag
        for frag in result.fragments:
            flags_tag = frag.data[6]  # Offset to flags/tag byte
            tag = flags_tag & 0x07
            assert tag == 5

    def test_packet_sequence_wraps(self):
        builder = MCTPBuilder()
        payload = bytes(600)  # Need 6 fragments, sequence wraps at 4

        result = builder.build_fragmented(
            dest_eid=1,
            msg_type=0x04,
            payload=payload,
        )

        sequences = [f.sequence for f in result.fragments]
        assert sequences == [0, 1, 2, 3, 0, 1]


class TestMessageReassembler:
    """Tests for message reassembly."""

    def test_single_fragment_reassembly(self):
        reassembler = MessageReassembler()

        # Single fragment with SOM and EOM
        payload = b"test data"
        result = reassembler.process_fragment(
            payload=payload,
            msg_tag=0,
            src_eid=1,
            pkt_seq=0,
            som=True,
            eom=True,
        )

        assert result == payload

    def test_two_fragment_reassembly(self):
        reassembler = MessageReassembler()

        # First fragment
        result = reassembler.process_fragment(
            payload=b"first ",
            msg_tag=0,
            src_eid=1,
            pkt_seq=0,
            som=True,
            eom=False,
        )
        assert result is None
        assert reassembler.pending_count() == 1

        # Second fragment
        result = reassembler.process_fragment(
            payload=b"second",
            msg_tag=0,
            src_eid=1,
            pkt_seq=1,
            som=False,
            eom=True,
        )
        assert result == b"first second"
        assert reassembler.pending_count() == 0

    def test_out_of_sequence_error(self):
        reassembler = MessageReassembler()

        # First fragment
        reassembler.process_fragment(
            payload=b"first",
            msg_tag=0,
            src_eid=1,
            pkt_seq=0,
            som=True,
            eom=False,
        )

        # Wrong sequence - should fail
        with pytest.raises(ValueError, match="Sequence error"):
            reassembler.process_fragment(
                payload=b"wrong",
                msg_tag=0,
                src_eid=1,
                pkt_seq=3,  # Should be 1
                som=False,
                eom=False,
            )

    def test_missing_som_error(self):
        reassembler = MessageReassembler()

        # Fragment without SOM for new message
        with pytest.raises(ValueError, match="without SOM"):
            reassembler.process_fragment(
                payload=b"orphan",
                msg_tag=0,
                src_eid=1,
                pkt_seq=0,
                som=False,
                eom=False,
            )

    def test_reset(self):
        reassembler = MessageReassembler()

        # Start a message
        reassembler.process_fragment(
            payload=b"start",
            msg_tag=0,
            src_eid=1,
            pkt_seq=0,
            som=True,
            eom=False,
        )
        assert reassembler.pending_count() == 1

        reassembler.reset()
        assert reassembler.pending_count() == 0


class TestFragmentationConfig:
    """Tests for fragmentation configuration."""

    def test_default_values(self):
        config = FragmentationConfig()
        assert config.max_tx_payload == FragmentationConstants.MAX_TX_PAYLOAD
        assert (
            config.inter_fragment_delay_ms == FragmentationConstants.DEFAULT_INTER_FRAGMENT_DELAY_MS
        )

    def test_validation_tx_payload(self):
        config = FragmentationConfig(max_tx_payload=200)  # Over limit
        with pytest.raises(ValueError, match="exceeds hardware limit"):
            config.validate()

    def test_validation_delay(self):
        config = FragmentationConfig(inter_fragment_delay_ms=-1)
        with pytest.raises(ValueError, match="cannot be negative"):
            config.validate()

    def test_validation_max_delay(self):
        config = FragmentationConfig(inter_fragment_delay_ms=500)  # Too long
        with pytest.raises(ValueError, match="exceeds maximum"):
            config.validate()


class TestMockTransportFragmentation:
    """Tests for MockTransport fragmentation support."""

    def test_set_large_vpd(self):
        mock = MockTransport()
        mock.set_large_vpd(512)
        assert len(mock.state.vpd_data) == 512

    def test_timing_summary_empty(self):
        mock = MockTransport()
        summary = mock.get_timing_summary()
        assert summary["fragment_count"] == 0

    def test_fragment_tracking(self):
        """Test that fragment timings are recorded."""
        mock = MockTransport()
        sphinx = Sphinx(mock)

        # Make a request
        result = sphinx.nvme_mi.health_status_poll(eid=1)
        assert result.success

        # Should have recorded the exchange
        assert len(mock.sent_packets) == 1
        assert len(mock.response_log) == 1

    def test_fragmented_transport_mixin(self):
        """Test that mixin is properly integrated."""
        mock = MockTransport()

        # Should have fragmentation config
        assert hasattr(mock, "_frag_config")
        assert hasattr(mock, "_reassembler")

        # Should be able to set delay
        mock.set_inter_fragment_delay(10.0)
        assert mock._frag_config.inter_fragment_delay_ms == 10.0


class TestNVMeMIFragmentation:
    """Tests for NVMe-MI specific fragmentation."""

    def test_build_nvme_mi_fragmented_small(self):
        builder = MCTPBuilder()
        payload = b"\x01\x00\x00\x00"  # Health poll

        result = builder.build_nvme_mi_fragmented(
            dest_eid=1,
            payload=payload,
        )

        assert result.fragment_count == 1

    def test_build_nvme_mi_fragmented_large(self):
        builder = MCTPBuilder()
        # Large VPD write or similar
        payload = bytes(300)

        result = builder.build_nvme_mi_fragmented(
            dest_eid=1,
            payload=payload,
        )

        assert result.is_fragmented
        assert result.fragment_count >= 3


class TestEndToEndFragmentation:
    """End-to-end tests with Sphinx and fragmented messages."""

    def test_large_vpd_read(self):
        """Test reading large VPD that might need fragmented response."""
        mock = MockTransport()
        mock.set_large_vpd(256)
        sphinx = Sphinx(mock)

        result = sphinx.nvme_mi.vpd_read(offset=0, length=256, eid=1)
        assert result.success
        assert "VPD Content" in result.fields or "VPD Data Length" in result.fields

    def test_normal_operations_unaffected(self):
        """Ensure fragmentation support doesn't affect normal operations."""
        mock = MockTransport()
        sphinx = Sphinx(mock)

        # All standard operations should work
        assert sphinx.nvme_mi.health_status_poll(eid=1).success
        assert sphinx.nvme_mi.get_subsystem_info(eid=1).success
        assert sphinx.nvme_mi.get_controller_list(eid=1).success


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
