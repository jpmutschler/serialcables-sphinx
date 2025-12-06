#!/usr/bin/env python3
"""
Instrumented hardware test with detailed logging for characterizing real device behavior.

Captures:
- Response times for each command
- Raw TX/RX packet bytes
- Parsed response structure
- Error patterns
- HYDRA MCTPResponse details

Use this data to tune MockTransport responses to match real hardware.

Usage:
    python -m examples.instrumented_test --port /dev/ttyUSB0 --slot 1
    python -m examples.instrumented_test --port COM13 --slot 1 --output capture.json
    python -m examples.instrumented_test --mock  # Test the instrumentation itself
"""

from __future__ import annotations
import argparse
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Optional, Any
from contextlib import contextmanager

from serialcables_sphinx import Sphinx, NVMeMIOpcode
from serialcables_sphinx.mctp.parser import MCTPParser
from serialcables_sphinx.mctp.builder import MCTPBuilder

# Try to import real HYDRA transport
try:
    from serialcables_sphinx.transports.hydra import HYDRATransport, HYDRAPacketResult
    from serialcables_hydra import JBOFController, MCTPResponse
    HAVE_HYDRA = True
except ImportError:
    HAVE_HYDRA = False
    MCTPResponse = None
    HYDRAPacketResult = None


@dataclass
class PacketCapture:
    """Single packet capture with timing."""
    direction: str  # "TX" or "RX"
    timestamp: float  # Unix timestamp
    timestamp_iso: str  # ISO format for readability
    data_hex: str  # Space-separated hex
    data_len: int
    
    # Parsed fields (for RX packets)
    smbus_addr: Optional[int] = None
    byte_count: Optional[int] = None
    mctp_dest_eid: Optional[int] = None
    mctp_src_eid: Optional[int] = None
    msg_type: Optional[int] = None
    pec: Optional[int] = None
    pec_valid: Optional[bool] = None


@dataclass
class HYDRAResponseCapture:
    """Capture of HYDRA MCTPResponse details."""
    success: bool
    packets_sent: int
    response_packet_count: int
    raw_response: str
    latency_ms: float


@dataclass 
class CommandCapture:
    """Complete command/response exchange."""
    command_name: str
    opcode: int
    opcode_hex: str
    eid: int
    slot: int
    
    # Timing
    start_time: float
    end_time: float
    latency_ms: float
    
    # Packets
    tx_packet: PacketCapture
    rx_packet: Optional[PacketCapture] = None
    
    # HYDRA-specific response data
    hydra_response: Optional[HYDRAResponseCapture] = None
    
    # Response
    success: bool = False
    status_code: Optional[int] = None
    status_name: Optional[str] = None
    decoded_fields: dict = field(default_factory=dict)
    decode_errors: List[str] = field(default_factory=list)
    
    # Errors
    error: Optional[str] = None


@dataclass
class TestSession:
    """Complete test session data."""
    start_time: str
    end_time: Optional[str] = None
    port: Optional[str] = None
    slot: int = 1
    is_mock: bool = False
    hydra_version: Optional[str] = None
    sphinx_version: Optional[str] = None
    
    # Statistics
    total_commands: int = 0
    successful_commands: int = 0
    failed_commands: int = 0
    
    # Timing stats
    min_latency_ms: float = float('inf')
    max_latency_ms: float = 0.0
    avg_latency_ms: float = 0.0
    
    # Captures
    captures: List[CommandCapture] = field(default_factory=list)
    
    def update_stats(self):
        """Recalculate statistics from captures."""
        self.total_commands = len(self.captures)
        self.successful_commands = sum(1 for c in self.captures if c.success)
        self.failed_commands = self.total_commands - self.successful_commands
        
        latencies = [c.latency_ms for c in self.captures if c.latency_ms > 0]
        if latencies:
            self.min_latency_ms = min(latencies)
            self.max_latency_ms = max(latencies)
            self.avg_latency_ms = sum(latencies) / len(latencies)


class InstrumentedTransport:
    """
    Wrapper transport that captures all packets with timing.
    
    When wrapping HYDRATransport, also captures MCTPResponse details.
    """
    
    def __init__(self, inner_transport, session: TestSession, slot: int = 1):
        self._inner = inner_transport
        self._session = session
        self._slot = slot
        self._parser = MCTPParser()
        self._current_capture: Optional[CommandCapture] = None
        
        # Check if inner transport is HYDRATransport (has last_result property)
        self._is_hydra = hasattr(inner_transport, 'last_result')
    
    def send_packet(self, packet: bytes) -> bytes:
        """Send packet and capture timing/data."""
        # Record TX
        tx_time = time.time()
        tx_capture = PacketCapture(
            direction="TX",
            timestamp=tx_time,
            timestamp_iso=datetime.fromtimestamp(tx_time).isoformat(),
            data_hex=packet.hex(' '),
            data_len=len(packet),
            smbus_addr=packet[0] if len(packet) > 0 else None,
            byte_count=packet[2] if len(packet) > 2 else None,
        )
        
        # Extract opcode from packet if this is NVMe-MI
        opcode = packet[8] if len(packet) > 8 else 0
        opcode_name = NVMeMIOpcode.decode(opcode)
        
        # Start command capture
        self._current_capture = CommandCapture(
            command_name=opcode_name,
            opcode=opcode,
            opcode_hex=f"0x{opcode:02X}",
            eid=packet[4] if len(packet) > 4 else 0,
            slot=self._slot,
            start_time=tx_time,
            end_time=0,
            latency_ms=0,
            tx_packet=tx_capture,
        )
        
        print(f"\n{'─'*60}")
        print(f"[TX] {opcode_name} (0x{opcode:02X})")
        print(f"     Packet ({len(packet)} bytes): {packet.hex(' ')}")
        
        # Send via inner transport
        try:
            response = self._inner.send_packet(packet)
            rx_time = time.time()
            
            # Record RX
            rx_capture = self._parse_rx_packet(response, rx_time)
            
            # Complete capture
            self._current_capture.end_time = rx_time
            self._current_capture.latency_ms = (rx_time - tx_time) * 1000
            self._current_capture.rx_packet = rx_capture
            self._current_capture.success = True
            
            # Capture HYDRA-specific data if available
            if self._is_hydra and self._inner.last_result is not None:
                hydra_result = self._inner.last_result
                self._current_capture.hydra_response = HYDRAResponseCapture(
                    success=hydra_result.success,
                    packets_sent=hydra_result.packets_sent,
                    response_packet_count=1,  # Could parse from raw_response
                    raw_response=hydra_result.raw_response[:200],  # Truncate for JSON
                    latency_ms=hydra_result.latency_ms,
                )
                
                # Use HYDRA's more accurate timing
                self._current_capture.latency_ms = hydra_result.latency_ms
            
            print(f"[RX] Response ({len(response)} bytes): {response.hex(' ')}")
            print(f"     Latency: {self._current_capture.latency_ms:.2f} ms")
            
            if rx_capture.pec_valid is not None:
                pec_status = "✓ valid" if rx_capture.pec_valid else "✗ INVALID"
                print(f"     PEC: 0x{rx_capture.pec:02X} ({pec_status})")
            
            # Show HYDRA details if available
            if self._current_capture.hydra_response:
                hr = self._current_capture.hydra_response
                print(f"     HYDRA: packets_sent={hr.packets_sent}")
            
            return response
            
        except Exception as e:
            rx_time = time.time()
            self._current_capture.end_time = rx_time
            self._current_capture.latency_ms = (rx_time - tx_time) * 1000
            self._current_capture.success = False
            self._current_capture.error = str(e)
            
            # Capture HYDRA error details if available
            if self._is_hydra and self._inner.last_result is not None:
                hydra_result = self._inner.last_result
                self._current_capture.hydra_response = HYDRAResponseCapture(
                    success=hydra_result.success,
                    packets_sent=hydra_result.packets_sent,
                    response_packet_count=0,
                    raw_response=hydra_result.raw_response[:200],
                    latency_ms=hydra_result.latency_ms,
                )
                print(f"     HYDRA raw: {hydra_result.raw_response[:100]}")
            
            print(f"[ERROR] {e}")
            print(f"     Latency: {self._current_capture.latency_ms:.2f} ms")
            raise
        
        finally:
            # Add to session
            self._session.captures.append(self._current_capture)
            self._current_capture = None
    
    def _parse_rx_packet(self, data: bytes, timestamp: float) -> PacketCapture:
        """Parse received packet for detailed logging."""
        capture = PacketCapture(
            direction="RX",
            timestamp=timestamp,
            timestamp_iso=datetime.fromtimestamp(timestamp).isoformat(),
            data_hex=data.hex(' '),
            data_len=len(data),
        )
        
        if len(data) >= 8:
            capture.smbus_addr = data[0]
            capture.byte_count = data[2] if len(data) > 2 else None
            capture.mctp_dest_eid = data[4] if len(data) > 4 else None
            capture.mctp_src_eid = data[5] if len(data) > 5 else None
            capture.msg_type = data[7] & 0x7F if len(data) > 7 else None
            
            # Check PEC
            if capture.byte_count:
                expected_end = 3 + capture.byte_count
                if len(data) > expected_end:
                    capture.pec = data[expected_end]
                    calculated = MCTPBuilder.calculate_pec(data[:expected_end])
                    capture.pec_valid = (calculated == capture.pec)
        
        return capture
    
    def set_target(self, slot: Optional[int] = None, address: Optional[int] = None):
        """Pass through to inner transport."""
        if slot is not None:
            self._slot = slot
        if hasattr(self._inner, 'set_target'):
            self._inner.set_target(slot=slot, address=address)
    
    def update_capture_with_decode(self, capture: CommandCapture, result):
        """Update capture with decoded response info."""
        capture.status_code = result.status_code
        capture.status_name = result.status.name if hasattr(result.status, 'name') else str(result.status)
        capture.success = result.success
        capture.decoded_fields = {
            name: {
                "value": str(fld.value),
                "raw_hex": fld.raw.hex() if fld.raw else "",
                "unit": fld.unit,
            }
            for name, fld in result.fields.items()
        }
        capture.decode_errors = result.decode_errors


def run_test_suite(sphinx: Sphinx, transport: InstrumentedTransport, eid: int = 1):
    """Run comprehensive test suite with instrumentation."""
    
    print("\n" + "=" * 60)
    print("INSTRUMENTED TEST SUITE")
    print("=" * 60)
    
    tests = [
        ("Health Status Poll", lambda: sphinx.nvme_mi.health_status_poll(eid=eid)),
        ("Subsystem Info", lambda: sphinx.nvme_mi.get_subsystem_info(eid=eid)),
        ("Controller List", lambda: sphinx.nvme_mi.get_controller_list(eid=eid)),
        ("Port Info", lambda: sphinx.nvme_mi.get_port_info(port_id=0, eid=eid)),
        ("VPD Read (small)", lambda: sphinx.nvme_mi.vpd_read(offset=0, length=64, eid=eid)),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{'━'*60}")
        print(f"TEST: {test_name}")
        print(f"{'━'*60}")
        
        try:
            result = test_func()
            
            # Update the last capture with decode info
            if transport._session.captures:
                last_capture = transport._session.captures[-1]
                transport.update_capture_with_decode(last_capture, result)
            
            # Print decoded result summary
            print(f"\n[DECODE] Status: {result.status_code} ({result.status})")
            print(f"         Success: {result.success}")
            
            if result.fields:
                print(f"         Fields ({len(result.fields)}):")
                for name, fld in list(result.fields.items())[:5]:  # First 5 fields
                    print(f"           {name}: {fld.value}")
                if len(result.fields) > 5:
                    print(f"           ... and {len(result.fields) - 5} more")
            
            if result.decode_errors:
                print(f"         Decode errors: {result.decode_errors}")
            
            results.append((test_name, True, result))
            
        except Exception as e:
            print(f"\n[FAILED] {e}")
            results.append((test_name, False, str(e)))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, success, _ in results if success)
    print(f"Passed: {passed}/{len(results)}")
    
    for test_name, success, _ in results:
        status = "✓" if success else "✗"
        print(f"  {status} {test_name}")
    
    return results


def print_session_stats(session: TestSession):
    """Print session statistics."""
    session.update_stats()
    
    print("\n" + "=" * 60)
    print("SESSION STATISTICS")
    print("=" * 60)
    
    print(f"Port: {session.port or 'Mock'}")
    print(f"Slot: {session.slot}")
    print(f"Mock mode: {session.is_mock}")
    print(f"\nCommands:")
    print(f"  Total: {session.total_commands}")
    print(f"  Successful: {session.successful_commands}")
    print(f"  Failed: {session.failed_commands}")
    
    if session.total_commands > 0:
        print(f"\nLatency (ms):")
        print(f"  Min: {session.min_latency_ms:.2f}")
        print(f"  Max: {session.max_latency_ms:.2f}")
        print(f"  Avg: {session.avg_latency_ms:.2f}")
    
    # Per-command timing breakdown
    print(f"\nPer-Command Timing:")
    for capture in session.captures:
        status = "✓" if capture.success else "✗"
        print(f"  {status} {capture.command_name}: {capture.latency_ms:.2f} ms")


def save_session(session: TestSession, filepath: str):
    """Save session data to JSON file."""
    session.update_stats()
    session.end_time = datetime.now().isoformat()
    
    # Convert to serializable dict
    data = asdict(session)
    
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    
    print(f"\nSession data saved to: {filepath}")


def main():
    parser = argparse.ArgumentParser(
        description="Instrumented HYDRA hardware test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-p", "--port",
        default="/dev/ttyUSB0",
        help="Serial port for HYDRA (default: /dev/ttyUSB0)",
    )
    parser.add_argument(
        "-s", "--slot",
        type=int,
        default=1,
        help="Target slot number 1-8 (default: 1)",
    )
    parser.add_argument(
        "-e", "--eid",
        type=int,
        default=1,
        help="Target Endpoint ID (default: 1)",
    )
    parser.add_argument(
        "-t", "--timeout",
        type=float,
        default=2.0,
        help="MCTP response timeout in seconds (default: 2.0)",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output JSON file for captured data",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock transport (for testing instrumentation)",
    )
    parser.add_argument(
        "--mock-delay",
        type=float,
        default=5.0,
        help="Mock response delay in ms (default: 5.0)",
    )
    
    args = parser.parse_args()
    
    # Get version info
    try:
        import serialcables_sphinx
        sphinx_version = getattr(serialcables_sphinx, '__version__', 'unknown')
    except:
        sphinx_version = 'unknown'
    
    try:
        import serialcables_hydra
        hydra_version = getattr(serialcables_hydra, '__version__', 'unknown')
    except:
        hydra_version = 'not installed'
    
    # Create session
    session = TestSession(
        start_time=datetime.now().isoformat(),
        port=None if args.mock else args.port,
        slot=args.slot,
        is_mock=args.mock,
        sphinx_version=sphinx_version,
        hydra_version=hydra_version,
    )
    
    print("=" * 60)
    print("INSTRUMENTED HARDWARE TEST")
    print("=" * 60)
    print(f"Time: {session.start_time}")
    print(f"Sphinx version: {sphinx_version}")
    print(f"HYDRA version: {hydra_version}")
    
    # Create transport
    if args.mock or not HAVE_HYDRA:
        if not args.mock and not HAVE_HYDRA:
            print("\n⚠ serialcables-hydra not installed, using mock transport")
            session.is_mock = True
        
        from serialcables_sphinx.transports.mock import MockTransport
        inner_transport = MockTransport()
        inner_transport.state.response_delay_ms = args.mock_delay
        print(f"Transport: MockTransport (delay={args.mock_delay}ms)")
    else:
        print(f"\nConnecting to HYDRA on {args.port}...")
        jbof = JBOFController(port=args.port)
        inner_transport = HYDRATransport(jbof, slot=args.slot, timeout=args.timeout)
        print(f"Transport: HYDRATransport ({args.port}, slot={args.slot}, timeout={args.timeout}s)")
    
    # Wrap with instrumentation
    instrumented = InstrumentedTransport(inner_transport, session, slot=args.slot)
    
    # Create Sphinx with instrumented transport
    sphinx = Sphinx(instrumented)
    
    # Run test suite
    try:
        run_test_suite(sphinx, instrumented, eid=args.eid)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nTest failed with error: {e}")
    
    # Print statistics
    print_session_stats(session)
    
    # Save if output specified
    if args.output:
        save_session(session, args.output)
    
    # Print raw packet summary for analysis
    print("\n" + "=" * 60)
    print("RAW PACKET SUMMARY (for MockTransport tuning)")
    print("=" * 60)
    
    for i, capture in enumerate(session.captures, 1):
        print(f"\n[{i}] {capture.command_name}")
        print(f"    TX: {capture.tx_packet.data_hex}")
        if capture.rx_packet:
            print(f"    RX: {capture.rx_packet.data_hex}")
            print(f"    Latency: {capture.latency_ms:.2f} ms")
        if capture.hydra_response:
            hr = capture.hydra_response
            print(f"    HYDRA: success={hr.success}, packets_sent={hr.packets_sent}")
        if capture.error:
            print(f"    ERROR: {capture.error}")
    
    return 0 if session.failed_commands == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
