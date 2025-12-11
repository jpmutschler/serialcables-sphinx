"""
Main Sphinx client - entry point for MCTP/NVMe-MI operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from serialcables_sphinx.mctp.builder import MCTPBuilder
from serialcables_sphinx.mctp.parser import MCTPParser
from serialcables_sphinx.nvme_mi.client import NVMeMIClient
from serialcables_sphinx.nvme_mi.decoder import NVMeMIDecoder

if TYPE_CHECKING:
    from serialcables_sphinx.transports.base import MCTPTransport


class Sphinx:
    """
    Main Sphinx client for MCTP and NVMe-MI operations.

    Sphinx handles the protocol layer (MCTP framing, NVMe-MI encoding/decoding)
    while delegating transport to HYDRA or other transport implementations.

    Attributes:
        transport: The underlying transport (e.g., HYDRADevice)
        mctp: MCTP packet builder for low-level access
        nvme_mi: NVMe-MI client for high-level commands

    Example:
        from serialcables_hydra import HYDRADevice
        from serialcables_sphinx import Sphinx

        # Connect to HYDRA
        hydra = HYDRADevice("/dev/ttyUSB0")

        # Create Sphinx client
        sphinx = Sphinx(hydra)

        # High-level API
        result = sphinx.nvme_mi.health_status_poll(eid=1)
        print(result.pretty_print())

        # Mid-level API - build packet manually
        packet = sphinx.mctp.build_nvme_mi_request(
            dest_eid=1,
            payload=bytes([0x01, 0x00, 0x00, 0x00])
        )
        print(f"Packet: {packet.hex(' ')}")
    """

    def __init__(
        self,
        transport: MCTPTransport,
        vendor_id: int | None = None,
        default_eid: int = 0,
        default_smbus_addr: int = 0x3A,
        src_eid: int = 0x00,
    ):
        """
        Initialize Sphinx client.

        Args:
            transport: Transport implementation (e.g., HYDRADevice)
            vendor_id: Optional vendor ID for vendor-specific decoding
            default_eid: Default Endpoint ID for commands
            default_smbus_addr: Default SMBus address for targets
            src_eid: Source Endpoint ID (typically 0x00 for host)
        """
        self._transport = transport
        self._vendor_id = vendor_id
        self._default_eid = default_eid

        # Initialize MCTP components
        self._mctp_builder = MCTPBuilder(
            smbus_addr=default_smbus_addr,
            src_eid=src_eid,
        )
        self._mctp_parser = MCTPParser()

        # Initialize NVMe-MI decoder
        self._nvme_mi_decoder = NVMeMIDecoder(vendor_id=vendor_id)

        # Initialize NVMe-MI client
        self._nvme_mi_client = NVMeMIClient(
            transport=transport,
            mctp_builder=self._mctp_builder,
            mctp_parser=self._mctp_parser,
            decoder=self._nvme_mi_decoder,
            default_eid=default_eid,
        )

    @property
    def transport(self) -> MCTPTransport:
        """Get underlying transport."""
        return self._transport

    @property
    def mctp(self) -> MCTPBuilder:
        """
        Get MCTP builder for low-level packet construction.

        Use this for building custom packets or debugging.

        Example:
            packet = sphinx.mctp.build_nvme_mi_request(
                dest_eid=1,
                payload=bytes([0x01, 0x00, 0x00, 0x00])
            )
        """
        return self._mctp_builder

    @property
    def mctp_parser(self) -> MCTPParser:
        """Get MCTP parser for response parsing."""
        return self._mctp_parser

    @property
    def nvme_mi(self) -> NVMeMIClient:
        """
        Get NVMe-MI client for high-level operations.

        Provides convenient methods for common NVMe-MI commands
        with automatic packet building, sending, and decoding.

        Example:
            result = sphinx.nvme_mi.health_status_poll(eid=1)
            print(result['Composite Temperature'])
        """
        return self._nvme_mi_client

    @property
    def decoder(self) -> NVMeMIDecoder:
        """Get NVMe-MI decoder for manual decoding."""
        return self._nvme_mi_decoder

    @property
    def vendor_id(self) -> int | None:
        """Get configured vendor ID."""
        return self._vendor_id

    # =========================================================================
    # Convenience Methods
    # =========================================================================

    def send_raw_packet(self, packet: bytes) -> bytes:
        """
        Send raw packet bytes via transport.

        Low-level method for sending pre-built packets.

        Args:
            packet: Complete MCTP packet bytes

        Returns:
            Raw response bytes
        """
        return self._transport.send_packet(packet)

    def set_target_slot(self, slot: int) -> None:
        """
        Set target slot (if transport supports it).

        For HYDRA, this configures the mux routing.

        Args:
            slot: Slot number
        """
        self._transport.set_target(slot=slot)

    def build_and_send(
        self,
        dest_eid: int,
        payload: bytes,
        integrity_check: bool = False,
    ) -> bytes:
        """
        Build MCTP packet and send.

        Mid-level convenience method.

        Args:
            dest_eid: Destination Endpoint ID
            payload: NVMe-MI payload bytes
            integrity_check: Enable integrity check

        Returns:
            Raw response bytes
        """
        packet = self._mctp_builder.build_nvme_mi_request(
            dest_eid=dest_eid,
            payload=payload,
            integrity_check=integrity_check,
        )
        return self._transport.send_packet(packet)

    # =========================================================================
    # CLI Format Helpers
    # =========================================================================

    def packet_to_cli(self, dest_eid: int, packet: bytes) -> str:
        """
        Convert packet to HYDRA CLI format.

        Args:
            dest_eid: Destination EID
            packet: Packet bytes

        Returns:
            CLI command string
        """
        return self._mctp_builder.to_cli_format(dest_eid, packet)

    # =========================================================================
    # Context Manager Support
    # =========================================================================

    def __enter__(self) -> Sphinx:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        # Transport cleanup if needed
        pass

    def __repr__(self) -> str:
        return f"Sphinx(transport={self._transport.__class__.__name__}, eid={self._default_eid})"
