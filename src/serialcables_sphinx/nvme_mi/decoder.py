"""
Main NVMe-MI decoder class.
"""

from __future__ import annotations

# Import decoders to register them
from serialcables_sphinx.nvme_mi import decoders as _  # noqa: F401
from serialcables_sphinx.nvme_mi.opcodes import NVMeMIOpcode
from serialcables_sphinx.nvme_mi.registry import DecoderRegistry
from serialcables_sphinx.nvme_mi.response import DecodedResponse
from serialcables_sphinx.nvme_mi.status import NVMeMIStatus


class NVMeMIDecoder:
    """
    Main decoder for NVMe-MI responses.

    Parses raw response bytes and delegates to appropriate
    registered decoders for field-level interpretation.

    Attributes:
        vendor_id: Optional vendor ID for vendor-specific decoding

    Example:
        decoder = NVMeMIDecoder()

        # Decode a response
        result = decoder.decode_response(
            raw_data=response_bytes,
            opcode=NVMeMIOpcode.NVM_SUBSYSTEM_HEALTH_STATUS_POLL
        )

        print(result.pretty_print())

        # With vendor extensions
        decoder = NVMeMIDecoder(vendor_id=0x1234)
        result = decoder.decode_response(raw_data, opcode=0xC0)
    """

    def __init__(self, vendor_id: int | None = None):
        """
        Initialize decoder with optional vendor ID.

        Args:
            vendor_id: PCI Vendor ID for vendor-specific extensions
        """
        self.vendor_id = vendor_id

    def decode_response(
        self,
        raw_data: bytes,
        opcode: int | NVMeMIOpcode,
        data_type: int | None = None,
    ) -> DecodedResponse:
        """
        Decode an NVMe-MI response.

        Args:
            raw_data: Raw response bytes (NVMe-MI payload after MCTP unwrap)
            opcode: The opcode that was sent
            data_type: For Read NVMe-MI Data Structure, the data type requested

        Returns:
            DecodedResponse with parsed fields
        """
        # Normalize opcode
        opcode_val = opcode.value if isinstance(opcode, NVMeMIOpcode) else opcode
        opcode_resolved: int | NVMeMIOpcode
        try:
            opcode_resolved = NVMeMIOpcode(opcode_val)
        except ValueError:
            opcode_resolved = opcode_val  # Keep as int for vendor-specific

        # Extract status from response header
        # NVMe-MI Response format: [MsgType/NVMeMIResponseType (1)][Status (1)][Reserved (2)][Data...]
        status_resolved: int | NVMeMIStatus
        if len(raw_data) < 4:
            status_resolved = NVMeMIStatus.UNSPECIFIED_ERROR
            payload = raw_data
        else:
            status_val = raw_data[1]
            try:
                status_resolved = NVMeMIStatus(status_val)
            except ValueError:
                status_resolved = status_val  # Keep raw value for unknown status

            # Payload starts after 4-byte MI response header
            payload = raw_data[4:]

        # Create response container
        response = DecodedResponse(
            opcode=opcode_resolved,
            status=status_resolved,
            raw_data=raw_data,
        )

        # Get appropriate decoder
        decoder = DecoderRegistry.get_decoder(
            opcode=opcode_val,
            data_type=data_type,
            vendor_id=self.vendor_id,
        )

        # Decode if we have a decoder and response was successful
        if decoder is not None:
            if response.success:
                try:
                    decoder.decode(payload, response)
                except Exception as e:
                    response.decode_errors.append(f"Decoder error: {e}")
            else:
                # Still try to decode error responses - some have useful data
                try:
                    decoder.decode(payload, response)
                except Exception:
                    pass  # Ignore decode errors for failed responses
        else:
            response.decode_errors.append(f"No decoder registered for opcode 0x{opcode_val:02X}")

        return response

    def decode_raw_hex(
        self,
        hex_str: str,
        opcode: int | NVMeMIOpcode,
        data_type: int | None = None,
        mctp_offset: int = 0,
    ) -> DecodedResponse:
        """
        Decode from hex string.

        Args:
            hex_str: Space-separated hex bytes
            opcode: The opcode that was sent
            data_type: Optional data structure type
            mctp_offset: Bytes to skip for MCTP framing (0 if already stripped)

        Returns:
            DecodedResponse

        Example:
            result = decoder.decode_raw_hex(
                "04 00 00 00 01 00 00 ...",  # NVMe-MI payload
                opcode=0x01
            )
        """
        # Parse hex string
        hex_str = hex_str.replace(",", " ")
        parts = hex_str.split()
        raw_bytes = bytes(int(p, 16) for p in parts)

        # Skip MCTP framing if specified
        if mctp_offset > 0:
            raw_bytes = raw_bytes[mctp_offset:]

        return self.decode_response(raw_bytes, opcode, data_type)

    def decode_mctp_response(
        self,
        mctp_payload: bytes,
        opcode: int | NVMeMIOpcode,
        data_type: int | None = None,
    ) -> DecodedResponse:
        """
        Decode NVMe-MI response from MCTP payload.

        The MCTP payload should start with the message type byte (0x04/0x84).

        Args:
            mctp_payload: MCTP message payload (after MCTP header)
            opcode: The opcode that was sent
            data_type: Optional data structure type

        Returns:
            DecodedResponse
        """
        # Verify message type
        if len(mctp_payload) < 1:
            response = DecodedResponse(
                opcode=opcode,
                status=NVMeMIStatus.UNSPECIFIED_ERROR,
                raw_data=mctp_payload,
            )
            response.decode_errors.append("Empty MCTP payload")
            return response

        msg_type = mctp_payload[0] & 0x7F
        if msg_type != 0x04:  # NVMe-MI message type
            response = DecodedResponse(
                opcode=opcode,
                status=NVMeMIStatus.UNSPECIFIED_ERROR,
                raw_data=mctp_payload,
            )
            response.decode_errors.append(f"Not an NVMe-MI message: type=0x{msg_type:02X}")
            return response

        # Skip message type byte, decode rest as NVMe-MI response
        nvme_mi_data = mctp_payload[1:]
        return self.decode_response(nvme_mi_data, opcode, data_type)
