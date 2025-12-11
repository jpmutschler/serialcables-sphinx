"""
High-level NVMe-MI client for easy interaction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from serialcables_sphinx.mctp.builder import MCTPBuilder
from serialcables_sphinx.mctp.parser import MCTPParser
from serialcables_sphinx.nvme_mi.constants import ConfigurationIdentifier, NVMeDataStructureType
from serialcables_sphinx.nvme_mi.decoder import NVMeMIDecoder
from serialcables_sphinx.nvme_mi.opcodes import NVMeMIOpcode
from serialcables_sphinx.nvme_mi.request import NVMeMIRequest
from serialcables_sphinx.nvme_mi.response import DecodedResponse

if TYPE_CHECKING:
    from serialcables_sphinx.transports.base import MCTPTransport


class NVMeMIClient:
    """
    High-level NVMe-MI client for common operations.

    Provides convenient methods for NVMe-MI commands with
    automatic packet building, sending, and decoding.

    Attributes:
        transport: MCTP transport (e.g., HYDRA device)
        decoder: NVMe-MI response decoder
        default_eid: Default Endpoint ID for commands

    Example:
        from serialcables_hydra import HYDRADevice
        from serialcables_sphinx import Sphinx

        hydra = HYDRADevice("/dev/ttyUSB0")
        sphinx = Sphinx(hydra)

        # Access NVMe-MI client
        result = sphinx.nvme_mi.health_status_poll(eid=1)
        print(result.pretty_print())
    """

    def __init__(
        self,
        transport: MCTPTransport,
        mctp_builder: MCTPBuilder,
        mctp_parser: MCTPParser,
        decoder: NVMeMIDecoder,
        default_eid: int = 0,
    ):
        """
        Initialize NVMe-MI client.

        Args:
            transport: MCTP transport implementation
            mctp_builder: MCTP packet builder
            mctp_parser: MCTP packet parser
            decoder: NVMe-MI response decoder
            default_eid: Default Endpoint ID
        """
        self._transport = transport
        self._builder = mctp_builder
        self._parser = mctp_parser
        self._decoder = decoder
        self._default_eid = default_eid

    def _send_mi_command(
        self,
        eid: int,
        request: NVMeMIRequest,
        data_type: int | None = None,
    ) -> DecodedResponse:
        """
        Send MI command and decode response.

        Args:
            eid: Target Endpoint ID
            request: NVMe-MI request object
            data_type: Optional data structure type for decoding

        Returns:
            Decoded response
        """
        # Build MCTP packet with NVMe-MI payload
        packet = self._builder.build_nvme_mi_request(
            dest_eid=eid,
            payload=request.pack(),
        )

        # Send via transport
        response_bytes = self._transport.send_packet(packet)

        # Parse MCTP response
        parsed = self._parser.parse(response_bytes)

        # Decode NVMe-MI response
        return self._decoder.decode_mctp_response(
            mctp_payload=bytes([parsed.msg_type | (0x80 if parsed.integrity_check else 0)])
            + parsed.payload,
            opcode=request.opcode,
            data_type=data_type,
        )

    # =========================================================================
    # Health Status Commands
    # =========================================================================

    def health_status_poll(self, eid: int | None = None) -> DecodedResponse:
        """
        Poll NVM Subsystem Health Status.

        Returns overall health including temperature, spare capacity,
        critical warnings, and controller status.

        Args:
            eid: Endpoint ID (uses default if not specified)

        Returns:
            DecodedResponse with health status fields
        """
        eid = eid if eid is not None else self._default_eid
        request = NVMeMIRequest.health_status_poll()
        return self._send_mi_command(eid, request)

    def controller_health_status(
        self,
        controller_id: int,
        eid: int | None = None,
    ) -> DecodedResponse:
        """
        Poll individual controller health status.

        Args:
            controller_id: NVMe Controller ID
            eid: Endpoint ID

        Returns:
            DecodedResponse with controller-specific health
        """
        eid = eid if eid is not None else self._default_eid
        request = NVMeMIRequest.controller_health_status(controller_id)
        return self._send_mi_command(eid, request)

    # =========================================================================
    # Data Structure Commands
    # =========================================================================

    def read_data_structure(
        self,
        data_type: int | NVMeDataStructureType,
        eid: int | None = None,
        port_id: int = 0,
        controller_id: int = 0,
    ) -> DecodedResponse:
        """
        Read NVMe-MI Data Structure.

        Args:
            data_type: Type of data structure to read
            eid: Endpoint ID
            port_id: Port ID (for port-specific structures)
            controller_id: Controller ID (for controller-specific structures)

        Returns:
            DecodedResponse with structure data
        """
        eid = eid if eid is not None else self._default_eid
        request = NVMeMIRequest.read_data_structure(
            data_type=data_type,
            port_id=port_id,
            controller_id=controller_id,
        )

        data_type_val = (
            data_type.value if isinstance(data_type, NVMeDataStructureType) else data_type
        )
        return self._send_mi_command(eid, request, data_type=data_type_val)

    def get_subsystem_info(self, eid: int | None = None) -> DecodedResponse:
        """
        Get NVM Subsystem Information.

        Convenience method for read_data_structure with NVM_SUBSYSTEM_INFORMATION type.

        Args:
            eid: Endpoint ID

        Returns:
            DecodedResponse with subsystem info
        """
        return self.read_data_structure(
            NVMeDataStructureType.NVM_SUBSYSTEM_INFORMATION,
            eid=eid,
        )

    def get_controller_list(self, eid: int | None = None) -> DecodedResponse:
        """
        Get list of controllers in subsystem.

        Args:
            eid: Endpoint ID

        Returns:
            DecodedResponse with controller IDs
        """
        return self.read_data_structure(
            NVMeDataStructureType.CONTROLLER_LIST,
            eid=eid,
        )

    def get_port_info(
        self,
        port_id: int = 0,
        eid: int | None = None,
    ) -> DecodedResponse:
        """
        Get Port Information.

        Args:
            port_id: Port ID to query
            eid: Endpoint ID

        Returns:
            DecodedResponse with port info
        """
        return self.read_data_structure(
            NVMeDataStructureType.PORT_INFORMATION,
            eid=eid,
            port_id=port_id,
        )

    # =========================================================================
    # Configuration Commands
    # =========================================================================

    def configuration_get(
        self,
        config_id: int | ConfigurationIdentifier,
        port_id: int = 0,
        eid: int | None = None,
    ) -> DecodedResponse:
        """
        Get Configuration.

        Args:
            config_id: Configuration identifier
            port_id: Port ID (for port-specific configurations)
            eid: Endpoint ID

        Returns:
            DecodedResponse with configuration data
        """
        eid = eid if eid is not None else self._default_eid
        request = NVMeMIRequest.configuration_get(config_id, port_id)
        return self._send_mi_command(eid, request)

    def configuration_set(
        self,
        config_id: int | ConfigurationIdentifier,
        config_data: bytes,
        port_id: int = 0,
        eid: int | None = None,
    ) -> DecodedResponse:
        """
        Set Configuration.

        Args:
            config_id: Configuration identifier
            config_data: Configuration value data
            port_id: Port ID (for port-specific configurations)
            eid: Endpoint ID

        Returns:
            DecodedResponse (check success property)
        """
        eid = eid if eid is not None else self._default_eid
        request = NVMeMIRequest.configuration_set(config_id, config_data, port_id)
        return self._send_mi_command(eid, request)

    # =========================================================================
    # VPD Commands
    # =========================================================================

    def vpd_read(
        self,
        offset: int = 0,
        length: int = 256,
        eid: int | None = None,
    ) -> DecodedResponse:
        """
        Read Vital Product Data.

        Args:
            offset: Byte offset into VPD data
            length: Number of bytes to read
            eid: Endpoint ID

        Returns:
            DecodedResponse with VPD content
        """
        eid = eid if eid is not None else self._default_eid
        request = NVMeMIRequest.vpd_read(offset, length)
        return self._send_mi_command(eid, request)

    # =========================================================================
    # Other Commands
    # =========================================================================

    def mi_reset(self, eid: int | None = None) -> DecodedResponse:
        """
        Send MI Reset command.

        Args:
            eid: Endpoint ID

        Returns:
            DecodedResponse (check success property)
        """
        eid = eid if eid is not None else self._default_eid
        request = NVMeMIRequest.mi_reset()
        return self._send_mi_command(eid, request)

    def send_vendor_command(
        self,
        opcode: int,
        data: bytes = b"",
        eid: int | None = None,
    ) -> DecodedResponse:
        """
        Send vendor-specific command.

        Args:
            opcode: Vendor opcode (0xC0-0xFF)
            data: Vendor-specific data
            eid: Endpoint ID

        Returns:
            DecodedResponse
        """
        eid = eid if eid is not None else self._default_eid
        request = NVMeMIRequest.vendor_specific(opcode, data)
        return self._send_mi_command(eid, request)

    # =========================================================================
    # Discovery Helpers
    # =========================================================================

    def discover_subsystem(self, eid: int | None = None) -> dict:
        """
        Full subsystem discovery.

        Enumerates subsystem info, health, and all controllers.

        Args:
            eid: Endpoint ID

        Returns:
            Dictionary with complete subsystem information
        """
        eid = eid if eid is not None else self._default_eid
        subsystem_info: dict | None = None
        health_info: dict | None = None
        controllers: list[dict] = []

        # Get subsystem info
        info = self.get_subsystem_info(eid)
        if info.success:
            subsystem_info = info.to_dict()

        # Get health
        health = self.health_status_poll(eid)
        if health.success:
            health_info = health.to_dict()

        # Get controllers
        ctrl_list = self.get_controller_list(eid)
        if ctrl_list.success:
            controller_ids = ctrl_list.get("Controller IDs", [])
            for ctrlr_id in controller_ids:
                ctrl_health = self.controller_health_status(ctrlr_id, eid)
                controllers.append(
                    {
                        "id": ctrlr_id,
                        "health": ctrl_health.to_dict() if ctrl_health.success else None,
                    }
                )

        return {
            "eid": eid,
            "subsystem": subsystem_info,
            "health": health_info,
            "controllers": controllers,
        }

    # =========================================================================
    # Decode-Only Methods (for raw response data)
    # =========================================================================

    def decode(
        self,
        raw_data: bytes,
        opcode: int | NVMeMIOpcode,
        data_type: int | None = None,
    ) -> DecodedResponse:
        """
        Decode raw NVMe-MI response data.

        Use this when you have raw response bytes and just want decoding.

        Args:
            raw_data: Raw NVMe-MI response bytes
            opcode: The opcode that was sent
            data_type: Optional data structure type

        Returns:
            DecodedResponse with parsed fields
        """
        return self._decoder.decode_response(raw_data, opcode, data_type)

    def decode_hex(
        self,
        hex_str: str,
        opcode: int | NVMeMIOpcode,
        data_type: int | None = None,
    ) -> DecodedResponse:
        """
        Decode from hex string.

        Args:
            hex_str: Space-separated hex bytes
            opcode: The opcode that was sent
            data_type: Optional data structure type

        Returns:
            DecodedResponse
        """
        return self._decoder.decode_raw_hex(hex_str, opcode, data_type)
