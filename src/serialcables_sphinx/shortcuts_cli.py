#!/usr/bin/env python3
"""
CLI tool for MCTP firmware shortcut commands.

Provides quick access to NVMe drive info via HYDRA firmware commands.

Usage:
    sphinx-shortcuts --port COM13 serial 1       # Get serial number from slot 1
    sphinx-shortcuts --port COM13 health 1       # Get health status from slot 1
    sphinx-shortcuts --port COM13 scan           # Scan all slots for drives
    sphinx-shortcuts --port COM13 health-all     # Health check all slots
"""

import argparse
import json
import sys

try:
    from serialcables_hydra import JBOFController

    HAVE_HYDRA = True
except ImportError:
    HAVE_HYDRA = False

from serialcables_sphinx.shortcuts import MCTPShortcuts


def cmd_serial(shortcuts: MCTPShortcuts, args) -> int:
    """Get serial number from a slot."""
    result = shortcuts.get_serial_number(slot=args.slot, timeout=args.timeout)

    if args.json:
        data = {
            "slot": result.slot,
            "serial_number": result.serial_number,
            "success": result.success,
            "error": result.error,
        }
        print(json.dumps(data, indent=2))
    else:
        if result.success:
            print(f"Slot {result.slot}: {result.serial_number}")
        else:
            print(f"Slot {result.slot}: Error - {result.error}", file=sys.stderr)

    return 0 if result.success else 1


def cmd_health(shortcuts: MCTPShortcuts, args) -> int:
    """Get health status from a slot."""
    result = shortcuts.get_health_status(slot=args.slot, timeout=args.timeout)

    if args.json:
        data = {
            "slot": result.slot,
            "success": result.success,
            "temperature_kelvin": result.temperature_kelvin,
            "temperature_celsius": result.temperature_celsius,
            "available_spare": result.available_spare,
            "spare_threshold": result.spare_threshold,
            "percentage_used": result.percentage_used,
            "critical_warning": result.critical_warning,
            "is_healthy": result.is_healthy,
            "error": result.error,
        }
        print(json.dumps(data, indent=2))
    elif args.full and result.decoded:
        print(result.decoded.pretty_print())
    else:
        print(result.summary())

    return 0 if result.success else 1


def cmd_scan(shortcuts: MCTPShortcuts, args) -> int:
    """Scan all slots for drives."""
    results = shortcuts.scan_all_slots(timeout=args.timeout)

    if args.json:
        data = [
            {
                "slot": r.slot,
                "serial_number": r.serial_number,
                "success": r.success,
                "error": r.error,
            }
            for r in results
        ]
        print(json.dumps(data, indent=2))
    else:
        print("=" * 50)
        print("NVMe Drive Scan")
        print("=" * 50)
        for result in results:
            if result.success:
                print(f"Slot {result.slot}: {result.serial_number}")
            else:
                status = result.error or "No drive"
                print(f"Slot {result.slot}: [{status}]")
        print("=" * 50)

        found = sum(1 for r in results if r.success)
        print(f"Found {found}/8 drives")

    return 0


def cmd_health_all(shortcuts: MCTPShortcuts, args) -> int:
    """Health check all slots."""
    results = shortcuts.health_check_all_slots(timeout=args.timeout)

    if args.json:
        data = [
            {
                "slot": r.slot,
                "success": r.success,
                "temperature_celsius": r.temperature_celsius,
                "available_spare": r.available_spare,
                "percentage_used": r.percentage_used,
                "critical_warning": r.critical_warning,
                "is_healthy": r.is_healthy if r.success else None,
                "error": r.error,
            }
            for r in results
        ]
        print(json.dumps(data, indent=2))
    else:
        print("=" * 60)
        print("NVMe Health Summary")
        print("=" * 60)
        for result in results:
            print(result.summary())
        print("=" * 60)

        healthy = sum(1 for r in results if r.success and r.is_healthy)
        responding = sum(1 for r in results if r.success)
        print(f"Healthy: {healthy}/{responding} responding drives")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="MCTP firmware shortcut commands for HYDRA",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    sphinx-shortcuts --port COM13 serial 1       # Get serial number
    sphinx-shortcuts --port COM13 health 1       # Get health status
    sphinx-shortcuts --port COM13 health 1 --full  # Full decoded health
    sphinx-shortcuts --port COM13 scan           # Scan all slots
    sphinx-shortcuts --port COM13 health-all     # Health check all
    sphinx-shortcuts --port COM13 health-all --json  # JSON output
        """,
    )

    parser.add_argument(
        "-p",
        "--port",
        required=True,
        help="Serial port for HYDRA (e.g., COM13, /dev/ttyUSB0)",
    )
    parser.add_argument(
        "-t",
        "--timeout",
        type=float,
        default=3.0,
        help="Command timeout in seconds (default: 3.0)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Show full decoded response (for health command)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # serial command
    serial_parser = subparsers.add_parser("serial", help="Get drive serial number")
    serial_parser.add_argument("slot", type=int, help="Slot number (1-8)")

    # health command
    health_parser = subparsers.add_parser("health", help="Get drive health status")
    health_parser.add_argument("slot", type=int, help="Slot number (1-8)")

    # scan command
    subparsers.add_parser("scan", help="Scan all slots for drives")

    # health-all command
    subparsers.add_parser("health-all", help="Health check all slots")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if not HAVE_HYDRA:
        print("Error: serialcables-hydra not installed", file=sys.stderr)
        return 1

    # Connect to HYDRA
    try:
        jbof = JBOFController(port=args.port)
        shortcuts = MCTPShortcuts(jbof, timeout=args.timeout)
    except Exception as e:
        print(f"Error connecting to HYDRA: {e}", file=sys.stderr)
        return 1

    # Run command
    commands = {
        "serial": cmd_serial,
        "health": cmd_health,
        "scan": cmd_scan,
        "health-all": cmd_health_all,
    }

    return commands[args.command](shortcuts, args)


if __name__ == "__main__":
    sys.exit(main())
