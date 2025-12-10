"""
Transport interface definition.

Defines the protocol that HYDRA and other transports must implement.
Includes support for fragmented message transmission with timing control.
"""

from __future__ import annotations

import time
from typing import Protocol, runtime_checkable

from serialcables_sphinx.mctp.fragmentation import (
    FragmentationConfig,
    FragmentationConstants,
    FragmentedMessage,
    MessageReassembler,
)


@runtime_checkable
class MCTPTransport(Protocol):
    """
    Protocol (interface) that any MCTP transport must implement.

    HYDRA implements this interface, but so could other transports
    like direct I2C adapters or test fixtures.

    Example implementation:
        class HYDRADevice(MCTPTransport):
            def send_packet(self, packet: bytes) -> bytes:
                # Send via serial, return response
                ...

            def set_target(self, slot: int = None, address: int = None) -> None:
                # Configure mux routing
                ...
    """

    def send_packet(self, packet: bytes) -> bytes:
        """
        Send raw packet bytes and return raw response bytes.

        The packet should be a complete MCTP-over-SMBus frame,
        ready to be transmitted on the wire.

        Args:
            packet: Complete packet bytes (MCTP-framed)

        Returns:
            Raw response bytes from device

        Raises:
            TransportError: If communication fails
        """
        ...

    def set_target(
        self,
        slot: int | None = None,
        address: int | None = None,
    ) -> None:
        """
        Configure target routing (optional, transport-specific).

        For HYDRA, this would select the mux channel.
        Other transports may ignore this or use it differently.

        Args:
            slot: Physical slot number (if applicable)
            address: Bus address (if applicable)
        """
        ...


class FragmentedTransportMixin:
    """
    Mixin providing fragmented message sending capability.

    Transports can inherit from this to get fragmentation support
    with proper inter-fragment timing.
    """

    def __init__(self):
        self._frag_config = FragmentationConfig()
        self._reassembler = MessageReassembler()

    @property
    def fragmentation_config(self) -> FragmentationConfig:
        """Current fragmentation configuration."""
        return self._frag_config

    @fragmentation_config.setter
    def fragmentation_config(self, config: FragmentationConfig):
        config.validate()
        self._frag_config = config

    def set_inter_fragment_delay(self, delay_ms: float):
        """
        Set delay between fragment transmissions.

        Args:
            delay_ms: Delay in milliseconds (0-100)
        """
        if delay_ms < 0:
            raise ValueError("Delay cannot be negative")
        if delay_ms > FragmentationConstants.MAX_INTER_FRAGMENT_DELAY_MS:
            raise ValueError(
                f"Delay exceeds maximum ({FragmentationConstants.MAX_INTER_FRAGMENT_DELAY_MS}ms)"
            )
        self._frag_config.inter_fragment_delay_ms = delay_ms

    def send_fragmented(
        self,
        message: FragmentedMessage,
        collect_response: bool = True,
    ) -> bytes | None:
        """
        Send a fragmented message with proper timing.

        Sends all fragments with configured inter-fragment delay,
        then collects response (which may also be fragmented).

        Args:
            message: FragmentedMessage from MCTPBuilder.build_fragmented()
            collect_response: Whether to wait for and return response

        Returns:
            Response bytes (potentially reassembled) or None

        Raises:
            TransportError: If communication fails
            FragmentationError: If fragments fail to send in time
        """
        if not hasattr(self, "send_packet"):
            raise NotImplementedError("Transport must implement send_packet")

        delay_sec = self._frag_config.inter_fragment_delay_ms / 1000.0
        response = None

        for _i, fragment in enumerate(message.fragments):
            # Send fragment
            if fragment.is_last and collect_response:
                # Last fragment - expect response
                response = self.send_packet(fragment.data)
            else:
                # Not last fragment - send without waiting for full response
                # (device buffers until EOM)
                response = self.send_packet(fragment.data)

            # Inter-fragment delay (not after last)
            if not fragment.is_last and delay_sec > 0:
                time.sleep(delay_sec)

        return response

    def send_fragmented_with_timing(
        self,
        message: FragmentedMessage,
    ) -> tuple[bytes, list[float]]:
        """
        Send fragmented message and return response with timing data.

        Returns:
            Tuple of (response_bytes, list of per-fragment latencies in ms)
        """
        if not hasattr(self, "send_packet"):
            raise NotImplementedError("Transport must implement send_packet")

        delay_sec = self._frag_config.inter_fragment_delay_ms / 1000.0
        latencies: list[float] = []
        response: bytes = b""

        for _i, fragment in enumerate(message.fragments):
            start = time.perf_counter()
            response = self.send_packet(fragment.data)
            elapsed = (time.perf_counter() - start) * 1000
            latencies.append(elapsed)

            if not fragment.is_last and delay_sec > 0:
                time.sleep(delay_sec)

        return response, latencies


class TransportError(Exception):
    """Base exception for transport errors."""

    pass


class TimeoutError(TransportError):
    """Timeout waiting for response."""

    pass


class CommunicationError(TransportError):
    """Error in communication with device."""

    pass


class PECError(TransportError):
    """Packet Error Code validation failed."""

    pass


class FragmentationError(TransportError):
    """Error in message fragmentation or reassembly."""

    pass


class ReassemblyTimeoutError(FragmentationError):
    """Timed out waiting for all message fragments."""

    pass


class SequenceError(FragmentationError):
    """Fragment received out of sequence."""

    pass
