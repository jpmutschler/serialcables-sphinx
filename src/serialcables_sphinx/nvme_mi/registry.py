"""
Registry for NVMe-MI response decoders.

Allows registration of standard and vendor-specific decoders.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from serialcables_sphinx.nvme_mi.base_decoder import ResponseDecoder


class DecoderRegistry:
    """
    Registry for NVMe-MI response decoders.

    Manages decoder registration and lookup, supporting both
    standard opcodes and vendor-specific extensions.

    Decoders are registered with:
    - opcode: The NVMe-MI opcode they decode
    - data_type: Optional data structure type (for Read Data Structure)
    - vendor_id: Optional vendor ID for vendor-specific decoders

    Example:
        # Register a decoder using decorator
        @DecoderRegistry.register(opcode=0x01)
        class HealthStatusDecoder(ResponseDecoder):
            def decode(self, data, response):
                ...

        # Register vendor-specific decoder
        @DecoderRegistry.register(opcode=0xC0, vendor_id=0x1234)
        class VendorDecoder(ResponseDecoder):
            def decode(self, data, response):
                ...

        # Manual registration
        DecoderRegistry.register_decoder(
            opcode=0x02,
            decoder_class=ControllerHealthDecoder
        )

        # Lookup
        decoder = DecoderRegistry.get_decoder(opcode=0x01)
    """

    # Standard decoders: {(opcode, data_type): decoder_class}
    _decoders: dict[tuple[int, int | None], type[ResponseDecoder]] = {}

    # Vendor-specific decoders: {vendor_id: {(opcode, data_type): decoder_class}}
    _vendor_decoders: dict[int, dict[tuple[int, int | None], type[ResponseDecoder]]] = {}

    @classmethod
    def register(
        cls,
        opcode: int,
        data_type: int | None = None,
        vendor_id: int | None = None,
    ) -> Callable[[type[ResponseDecoder]], type[ResponseDecoder]]:
        """
        Decorator to register a decoder class.

        Args:
            opcode: NVMe-MI opcode this decoder handles
            data_type: Optional data structure type (for opcode 0x00)
            vendor_id: Optional vendor ID for vendor-specific decoders

        Returns:
            Decorator function

        Example:
            @DecoderRegistry.register(opcode=0x01)
            class HealthStatusDecoder(ResponseDecoder):
                ...
        """

        def decorator(decoder_cls: type[ResponseDecoder]) -> type[ResponseDecoder]:
            cls.register_decoder(opcode, decoder_cls, data_type, vendor_id)
            return decoder_cls

        return decorator

    @classmethod
    def register_decoder(
        cls,
        opcode: int,
        decoder_class: type[ResponseDecoder],
        data_type: int | None = None,
        vendor_id: int | None = None,
    ) -> None:
        """
        Register a decoder class.

        Args:
            opcode: NVMe-MI opcode
            decoder_class: Decoder class to register
            data_type: Optional data structure type
            vendor_id: Optional vendor ID
        """
        key = (opcode, data_type)

        if vendor_id is not None:
            if vendor_id not in cls._vendor_decoders:
                cls._vendor_decoders[vendor_id] = {}
            cls._vendor_decoders[vendor_id][key] = decoder_class
        else:
            cls._decoders[key] = decoder_class

    @classmethod
    def get_decoder(
        cls,
        opcode: int,
        data_type: int | None = None,
        vendor_id: int | None = None,
    ) -> ResponseDecoder | None:
        """
        Get decoder instance for given parameters.

        Lookup order:
        1. Vendor-specific decoder with exact match (opcode, data_type)
        2. Vendor-specific decoder with opcode only
        3. Standard decoder with exact match (opcode, data_type)
        4. Standard decoder with opcode only

        Args:
            opcode: NVMe-MI opcode
            data_type: Optional data structure type
            vendor_id: Optional vendor ID

        Returns:
            Decoder instance or None if not found
        """
        # Check vendor-specific first
        if vendor_id is not None and vendor_id in cls._vendor_decoders:
            vendor_decoders = cls._vendor_decoders[vendor_id]

            # Try exact match
            key = (opcode, data_type)
            if key in vendor_decoders:
                return vendor_decoders[key]()

            # Try opcode-only match
            key = (opcode, None)
            if key in vendor_decoders:
                return vendor_decoders[key]()

        # Standard decoders
        # Try exact match
        key = (opcode, data_type)
        if key in cls._decoders:
            return cls._decoders[key]()

        # Try opcode-only match
        key = (opcode, None)
        if key in cls._decoders:
            return cls._decoders[key]()

        return None

    @classmethod
    def has_decoder(
        cls,
        opcode: int,
        data_type: int | None = None,
        vendor_id: int | None = None,
    ) -> bool:
        """Check if a decoder is registered for the given parameters."""
        return cls.get_decoder(opcode, data_type, vendor_id) is not None

    @classmethod
    def list_decoders(cls) -> dict[str, list]:
        """
        List all registered decoders.

        Returns:
            Dictionary with 'standard' and 'vendor' decoder lists
        """
        standard = []
        for (opcode, data_type), decoder_cls in cls._decoders.items():
            standard.append(
                {
                    "opcode": f"0x{opcode:02X}",
                    "data_type": f"0x{data_type:02X}" if data_type is not None else None,
                    "decoder": decoder_cls.__name__,
                }
            )

        vendor = []
        for vendor_id, decoders in cls._vendor_decoders.items():
            for (opcode, data_type), decoder_cls in decoders.items():
                vendor.append(
                    {
                        "vendor_id": f"0x{vendor_id:04X}",
                        "opcode": f"0x{opcode:02X}",
                        "data_type": f"0x{data_type:02X}" if data_type is not None else None,
                        "decoder": decoder_cls.__name__,
                    }
                )

        return {"standard": standard, "vendor": vendor}

    @classmethod
    def clear(cls) -> None:
        """Clear all registered decoders. Mainly for testing."""
        cls._decoders.clear()
        cls._vendor_decoders.clear()
