#!/usr/bin/env python3
"""
Example: Using MCTP firmware shortcuts.

Demonstrates the high-level shortcuts interface for common NVMe operations.
These commands use HYDRA firmware v0.0.6+ built-in MCTP handling.

Usage:
    python -m examples.shortcuts_example --port COM13
    python -m examples.shortcuts_example --port /dev/ttyUSB0 --slot 1
"""

import argparse
import sys

try:
    from serialcables_hydra import JBOFController
    HAVE_HYDRA = True
except ImportError:
    HAVE_HYDRA = False

from serialcables_sphinx.shortcuts import MCTPShortcuts, create_shortcuts


def demonstrate_serial_number(shortcuts: MCTPShortcuts, slot: int):
    """Show serial number retrieval."""
    print("\n" + "=" * 60)
    print(f"SERIAL NUMBER (Slot {slot})")
    print("=" * 60)
    
    result = shortcuts.get_serial_number(slot=slot)
    
    if result.success:
        print(f"Serial Number: {result.serial_number}")
        print(f"Raw packets received: {len(result.raw_packets)}")
        
        if result.decoded:
            print("\nFull Sphinx decode available:")
            print(f"  Status: {result.decoded.status}")
    else:
        print(f"Error: {result.error}")


def demonstrate_health_status(shortcuts: MCTPShortcuts, slot: int):
    """Show health status retrieval with both quick-access and full decode."""
    print("\n" + "=" * 60)
    print(f"HEALTH STATUS (Slot {slot})")
    print("=" * 60)
    
    result = shortcuts.get_health_status(slot=slot)
    
    if result.success:
        # Quick-access values (from firmware parsing)
        print("\n--- Quick Access Values (Firmware Parsed) ---")
        print(f"Temperature: {result.temperature_celsius}°C ({result.temperature_kelvin} K)")
        print(f"Available Spare: {result.available_spare}%")
        print(f"Spare Threshold: {result.spare_threshold}%")
        print(f"Percentage Used: {result.percentage_used}%")
        print(f"Critical Warning: 0x{result.critical_warning:02X}" if result.critical_warning else "Critical Warning: None")
        print(f"Is Healthy: {result.is_healthy}")
        
        # One-line summary
        print(f"\nSummary: {result.summary()}")
        
        # Full Sphinx decode
        if result.decoded:
            print("\n--- Full Sphinx Decode ---")
            print(result.decoded.pretty_print())
    else:
        print(f"Error: {result.error}")
        
        # Some drives don't support health status
        if "unsupported" in (result.error or "").lower():
            print("\nNote: This drive may not support the NVMe-MI Health Status command.")
            print("Try using the raw packet approach instead.")


def demonstrate_scan(shortcuts: MCTPShortcuts):
    """Show scanning all slots."""
    print("\n" + "=" * 60)
    print("SLOT SCAN")
    print("=" * 60)
    
    results = shortcuts.scan_all_slots()
    
    print("\nSlot | Status           | Serial Number")
    print("-" * 50)
    
    found = 0
    for result in results:
        if result.success:
            print(f"  {result.slot}  | ✓ Present        | {result.serial_number}")
            found += 1
        else:
            error = result.error[:20] if result.error else "No response"
            print(f"  {result.slot}  | ✗ {error}")
    
    print("-" * 50)
    print(f"Found {found}/8 drives")


def demonstrate_health_summary(shortcuts: MCTPShortcuts):
    """Show health summary for all slots."""
    print("\n" + "=" * 60)
    print("HEALTH SUMMARY")
    print("=" * 60)
    
    shortcuts.print_health_summary()


def main():
    parser = argparse.ArgumentParser(
        description="MCTP shortcuts demonstration",
    )
    parser.add_argument(
        "-p", "--port",
        required=True,
        help="Serial port for HYDRA (e.g., COM13, /dev/ttyUSB0)",
    )
    parser.add_argument(
        "-s", "--slot",
        type=int,
        default=1,
        help="Target slot for detailed examples (default: 1)",
    )
    parser.add_argument(
        "-t", "--timeout",
        type=float,
        default=3.0,
        help="Command timeout in seconds (default: 3.0)",
    )
    parser.add_argument(
        "--scan-only",
        action="store_true",
        help="Only run slot scan",
    )
    
    args = parser.parse_args()
    
    if not HAVE_HYDRA:
        print("Error: serialcables-hydra not installed")
        print("Install with: pip install serialcables-hydra>=1.2.0")
        return 1
    
    print("=" * 60)
    print("MCTP SHORTCUTS DEMONSTRATION")
    print("=" * 60)
    print(f"Port: {args.port}")
    print(f"Timeout: {args.timeout}s")
    
    # Connect using convenience function
    try:
        shortcuts = create_shortcuts(args.port, timeout=args.timeout)
        print("Connected to HYDRA successfully")
    except Exception as e:
        print(f"Error connecting: {e}")
        return 1
    
    if args.scan_only:
        demonstrate_scan(shortcuts)
        return 0
    
    # Run demonstrations
    try:
        # First scan to see what's available
        demonstrate_scan(shortcuts)
        
        # Detailed examples on specified slot
        demonstrate_serial_number(shortcuts, args.slot)
        demonstrate_health_status(shortcuts, args.slot)
        
        # Health summary for all
        demonstrate_health_summary(shortcuts)
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 1
    except Exception as e:
        print(f"\n\nError: {e}")
        return 1
    
    print("\n" + "=" * 60)
    print("DEMONSTRATION COMPLETE")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
