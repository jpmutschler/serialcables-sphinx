"""
Base class for NVMe-MI response decoders.
"""

from __future__ import annotations

import struct
from abc import ABC, abstractmethod
from typing import Any

from serialcables_sphinx.nvme_mi.response import DecodedField, DecodedResponse


class ResponseDecoder(ABC):
    """
    Abstract base class for NVMe-MI response decoders.

    Implement this class to create decoders for specific
    NVMe-MI commands or vendor-specific responses.

    Example:
        from serialcables_sphinx import DecoderRegistry, ResponseDecoder

        @DecoderRegistry.register(opcode=0xC0, vendor_id=0x1234)
        class MyVendorDecoder(ResponseDecoder):
            def decode(self, data: bytes, response: DecodedResponse) -> DecodedResponse:
                self._add_field(response, "My Field", data[0], data[0:1])
                return response
    """

    @abstractmethod
    def decode(self, data: bytes, response: DecodedResponse) -> DecodedResponse:
        """
        Decode response data and populate fields.

        Args:
            data: Response payload bytes (after MI header)
            response: DecodedResponse to populate

        Returns:
            The populated DecodedResponse
        """
        pass

    def _add_field(
        self,
        response: DecodedResponse,
        name: str,
        value: Any,
        raw: bytes,
        unit: str = "",
        description: str = "",
    ) -> None:
        """
        Helper to add a decoded field to the response.

        Args:
            response: Response to add field to
            name: Field name (used as key and display name)
            value: Parsed value
            raw: Raw bytes for this field
            unit: Optional unit of measurement
            description: Optional description/interpretation
        """
        response.fields[name] = DecodedField(
            name=name,
            value=value,
            raw=raw,
            unit=unit,
            description=description,
        )

    def _safe_unpack(
        self,
        fmt: str,
        data: bytes,
        offset: int,
        response: DecodedResponse,
    ) -> tuple[Any, ...]:
        """
        Safely unpack bytes with error handling.

        If data is truncated, adds a decode error and returns zeros.

        Args:
            fmt: struct format string
            data: Data buffer
            offset: Byte offset into data
            response: Response for error logging

        Returns:
            Unpacked tuple (may be zeros if data truncated)
        """
        size = struct.calcsize(fmt)
        if offset + size > len(data):
            response.decode_errors.append(
                f"Truncated data at offset {offset}: need {size} bytes, have {len(data) - offset}"
            )
            # Return zeros as fallback
            return struct.unpack(fmt, bytes(size))
        return struct.unpack(fmt, data[offset : offset + size])

    def _safe_get_byte(
        self,
        data: bytes,
        offset: int,
        response: DecodedResponse,
        default: int = 0,
    ) -> int:
        """
        Safely get a single byte from data.

        Args:
            data: Data buffer
            offset: Byte offset
            response: Response for error logging
            default: Default value if offset out of range

        Returns:
            Byte value or default
        """
        if offset >= len(data):
            response.decode_errors.append(
                f"Data truncated at offset {offset}: buffer length {len(data)}"
            )
            return default
        return data[offset]

    def _safe_get_bytes(
        self,
        data: bytes,
        offset: int,
        length: int,
        response: DecodedResponse,
    ) -> bytes:
        """
        Safely get a byte slice from data.

        Args:
            data: Data buffer
            offset: Starting byte offset
            length: Number of bytes
            response: Response for error logging

        Returns:
            Byte slice (may be shorter than requested)
        """
        if offset >= len(data):
            response.decode_errors.append(
                f"Data truncated at offset {offset}: buffer length {len(data)}"
            )
            return b""

        available = len(data) - offset
        if available < length:
            response.decode_errors.append(
                f"Partial data at offset {offset}: requested {length} bytes, have {available}"
            )

        return data[offset : offset + length]

    def _decode_temperature(
        self,
        kelvin: int,
        report_not_available: bool = True,
    ) -> tuple[str, int | None]:
        """
        Decode temperature from Kelvin to Celsius with formatting.

        Args:
            kelvin: Temperature in Kelvin (0 = not reported)
            report_not_available: Include "Not reported" for 0

        Returns:
            Tuple of (display_string, celsius_value_or_none)
        """
        if kelvin == 0:
            if report_not_available:
                return "Not reported", None
            return "0 K", None

        celsius = kelvin - 273
        return f"{celsius}°C ({kelvin} K)", celsius

    def _decode_percentage(
        self,
        value: int,
        not_reported_value: int = 255,
    ) -> str:
        """
        Decode percentage value with formatting.

        Args:
            value: Raw percentage value
            not_reported_value: Value indicating "not reported"

        Returns:
            Formatted percentage string
        """
        if value == not_reported_value:
            return "Not reported"
        return f"{value}%"
