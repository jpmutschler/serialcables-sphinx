#!/usr/bin/env python3
"""
Live hardware testing example for HYDRA enclosure.

This example demonstrates using Sphinx with a real HYDRA device.
Use this once serialcables-hydra is installed and hardware is connected.

Prerequisites:
    pip install serialcables-sphinx serialcables-hydra

Usage:
    python -m examples.live_hardware_test --port /dev/ttyUSB0
    python -m examples.live_hardware_test --port COM3  # Windows
    python -m examples.live_hardware_test --mock       # Test without hardware
"""

import argparse
import sys
import json

from serialcables_sphinx import Sphinx

# Try to import real HYDRA transport
try:
    from serialcables_sphinx.transports.hydra import create_hydra_transport
    HAVE_HYDRA = True
except ImportError:
    HAVE_HYDRA = False


def scan_endpoints(sphinx: Sphinx, eid_range: range = range(1, 16)) -> list:
    """
    Scan for responding MCTP endpoints.
    
    Args:
        sphinx: Sphinx client
        eid_range: Range of EIDs to scan
        
    Returns:
        List of responding EIDs
    """
    responding = []
    
    print(f"Scanning EIDs {eid_range.start} to {eid_range.stop - 1}...")
    
    for eid in eid_range:
        try:
            result = sphinx.nvme_mi.health_status_poll(eid=eid)
            if result.success:
                responding.append(eid)
                print(f"  EID {eid}: ✓ Responding")
            else:
                print(f"  EID {eid}: ✗ Error (status 0x{result.status_code:02X})")
        except Exception as e:
            print(f"  EID {eid}: ✗ {e}")
    
    return responding


def full_device_report(sphinx: Sphinx, eid: int) -> dict:
    """
    Generate full device report.
    
    Args:
        sphinx: Sphinx client
        eid: Target Endpoint ID
        
    Returns:
        Dictionary with complete device information
    """
    report = {
        "eid": eid,
        "subsystem": None,
        "health": None,
        "port": None,
        "controllers": [],
        "vpd": None,
    }
    
    # Subsystem info
    print(f"\nReading subsystem info for EID {eid}...")
    info = sphinx.nvme_mi.get_subsystem_info(eid=eid)
    if info.success:
        report["subsystem"] = info.to_dict()
        print(f"  NVMe-MI Version: {info['NVMe-MI Version']}")
        print(f"  Ports: {info['Number of Ports']}")
    
    # Health status
    print("Reading health status...")
    health = sphinx.nvme_mi.health_status_poll(eid=eid)
    if health.success:
        report["health"] = health.to_dict()
        print(f"  Temperature: {health['Composite Temperature']}")
        print(f"  Available Spare: {health['Available Spare']}")
        print(f"  Life Used: {health['Drive Life Used']}")
    
    # Port info
    print("Reading port info...")
    port = sphinx.nvme_mi.get_port_info(port_id=0, eid=eid)
    if port.success:
        report["port"] = port.to_dict()
        print(f"  Port Type: {port['Port Type']}")
        print(f"  Max MTU: {port['Max MCTP Transmission Unit']}")
    
    # Controller list and health
    print("Enumerating controllers...")
    ctrl_list = sphinx.nvme_mi.get_controller_list(eid=eid)
    if ctrl_list.success:
        controller_ids = ctrl_list.get("Controller IDs", [])
        print(f"  Found {len(controller_ids)} controller(s)")
        
        for ctrl_id in controller_ids:
            ctrl_health = sphinx.nvme_mi.controller_health_status(ctrl_id, eid=eid)
            ctrl_info = {
                "id": ctrl_id,
                "health": ctrl_health.to_dict() if ctrl_health.success else None,
            }
            report["controllers"].append(ctrl_info)
            
            if ctrl_health.success:
                print(f"    Controller {ctrl_id}: Ready={ctrl_health['Controller Ready']}")
    
    # VPD
    print("Reading VPD...")
    vpd = sphinx.nvme_mi.vpd_read(offset=0, length=256, eid=eid)
    if vpd.success:
        report["vpd"] = vpd.to_dict()
        content = vpd.get("VPD Content", vpd.get("VPD Content (hex)", ""))
        print(f"  VPD: {content[:50]}...")
    
    return report


def main():
    parser = argparse.ArgumentParser(
        description="Live HYDRA hardware test",
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
        "--scan",
        action="store_true",
        help="Scan for responding endpoints",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate full device report",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock transport (for testing without hardware)",
    )
    
    args = parser.parse_args()
    
    # Banner
    print("=" * 60)
    print("SPHINX LIVE HARDWARE TEST")
    print("=" * 60)
    
    # Create transport
    if args.mock or not HAVE_HYDRA:
        if not args.mock and not HAVE_HYDRA:
            print("\n⚠ serialcables-hydra not installed, using mock transport")
        from serialcables_sphinx.transports.mock import MockTransport
        transport = MockTransport(verbose=True)
        print(f"Transport: MockTransport (simulated)")
    else:
        print(f"\nConnecting to HYDRA on {args.port}, slot {args.slot}...")
        transport = create_hydra_transport(
            args.port,
            slot=args.slot,
            verbose=True,
        )
        print(f"Transport: HYDRATransport ({args.port})")
    
    # Create Sphinx client
    sphinx = Sphinx(transport)
    
    # Scan mode
    if args.scan:
        endpoints = scan_endpoints(sphinx)
        print(f"\nResponding endpoints: {endpoints}")
        
        if args.json:
            print(json.dumps({"endpoints": endpoints}, indent=2))
        return 0
    
    # Report mode
    if args.report:
        report = full_device_report(sphinx, args.eid)
        
        if args.json:
            print("\n" + json.dumps(report, indent=2, default=str))
        return 0
    
    # Default: simple health check
    print(f"\n--- Health Status Poll (EID {args.eid}) ---")
    
    result = sphinx.nvme_mi.health_status_poll(eid=args.eid)
    
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, default=str))
    else:
        print(result.pretty_print())
    
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
