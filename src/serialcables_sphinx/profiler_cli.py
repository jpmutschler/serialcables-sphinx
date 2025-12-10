#!/usr/bin/env python3
"""
CLI tool for profiling NVMe devices and capturing responses.

Usage:
    sphinx-profile --port COM13 --slot 1 --output my_device.json
    sphinx-profile --port /dev/ttyUSB0 --slot 1 --name "Samsung 990 Pro"
    sphinx-profile --load my_device.json --summary
    sphinx-profile --load my_device.json --verify

This tool captures all read-only NVMe-MI commands from a real device
and saves them to a JSON file for use with MockTransport.
"""

import argparse
import json
import sys
from datetime import datetime


def cmd_capture(args) -> int:
    """Capture device profile."""
    try:
        from serialcables_sphinx.profiler import CaptureConfig, DeviceProfiler
    except ImportError as e:
        print(f"Error importing profiler: {e}", file=sys.stderr)
        return 1

    # Build config
    config = CaptureConfig(
        capture_health=not args.skip_health,
        capture_data_structures=not args.skip_data_struct,
        capture_configuration=not args.skip_config,
        capture_vpd=not args.skip_vpd,
        capture_admin_tunneled=not args.skip_admin,
        vpd_max_offset=args.vpd_max,
        vpd_chunk_size=args.vpd_chunk,
        command_delay_ms=args.delay,
        timeout=args.timeout,
        verbose=not args.quiet,
    )

    # Profile name
    if args.name:
        profile_name = args.name.replace(" ", "_")
    else:
        profile_name = f"device_{args.slot}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Output file
    if args.output:
        output_path = args.output
    else:
        output_path = f"{profile_name}.json"

    print("=" * 60)
    print("NVMe Device Profiler")
    print("=" * 60)
    print(f"Port: {args.port}")
    print(f"Slot: {args.slot}")
    print(f"EID: {args.eid}")
    print(f"Output: {output_path}")
    print("=" * 60)

    try:
        profiler = DeviceProfiler(
            port=args.port,
            slot=args.slot,
            eid=args.eid,
            config=config,
        )

        profile = profiler.capture_full_profile(profile_name=profile_name)
        profile.save(output_path, indent=2 if not args.compact else None)

        print(f"\nProfile saved to: {output_path}")
        return 0

    except KeyboardInterrupt:
        print("\n\nCapture interrupted by user")
        return 1
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        if args.debug:
            import traceback

            traceback.print_exc()
        return 1


def cmd_load(args) -> int:
    """Load and display profile information."""
    try:
        from serialcables_sphinx.profiler import DeviceProfile
    except ImportError as e:
        print(f"Error importing profiler: {e}", file=sys.stderr)
        return 1

    try:
        profile = DeviceProfile.load(args.load)
    except Exception as e:
        print(f"Error loading profile: {e}", file=sys.stderr)
        return 1

    if args.verify:
        if profile.verify_checksum():
            print("Checksum: VALID")
            return 0
        else:
            print("Checksum: INVALID - file may be corrupted")
            return 1

    if args.summary:
        print(profile.summary())
        return 0

    if args.json_output:
        print(json.dumps(profile.to_dict(), indent=2))
        return 0

    # Default: show summary
    print(profile.summary())
    return 0


def cmd_compare(args) -> int:
    """Compare two device profiles."""
    try:
        from serialcables_sphinx.profiler import DeviceProfile
    except ImportError as e:
        print(f"Error importing profiler: {e}", file=sys.stderr)
        return 1

    try:
        profile1 = DeviceProfile.load(args.profile1)
        profile2 = DeviceProfile.load(args.profile2)
    except Exception as e:
        print(f"Error loading profiles: {e}", file=sys.stderr)
        return 1

    print("=" * 60)
    print("Device Profile Comparison")
    print("=" * 60)

    # Basic info
    print(f"\nProfile 1: {profile1.profile_name}")
    print(f"  Device: {profile1.metadata.model_number or 'Unknown'}")
    print(f"  Serial: {profile1.metadata.serial_number or 'Unknown'}")
    print(f"  Commands: {len(profile1.get_all_commands())}")

    print(f"\nProfile 2: {profile2.profile_name}")
    print(f"  Device: {profile2.metadata.model_number or 'Unknown'}")
    print(f"  Serial: {profile2.metadata.serial_number or 'Unknown'}")
    print(f"  Commands: {len(profile2.get_all_commands())}")

    # Compare supported commands
    cmds1 = {(c.opcode, c.data_type, c.config_id) for c in profile1.get_all_commands() if c.success}
    cmds2 = {(c.opcode, c.data_type, c.config_id) for c in profile2.get_all_commands() if c.success}

    only_in_1 = cmds1 - cmds2
    only_in_2 = cmds2 - cmds1

    if only_in_1:
        print(f"\nOnly in Profile 1 ({len(only_in_1)}):")
        for opcode, dt, cfg in sorted(only_in_1):
            print(
                f"  Opcode 0x{opcode:02X}"
                + (f" DataType={dt}" if dt else "")
                + (f" Config={cfg}" if cfg else "")
            )

    if only_in_2:
        print(f"\nOnly in Profile 2 ({len(only_in_2)}):")
        for opcode, dt, cfg in sorted(only_in_2):
            print(
                f"  Opcode 0x{opcode:02X}"
                + (f" DataType={dt}" if dt else "")
                + (f" Config={cfg}" if cfg else "")
            )

    # Compare timing
    print("\nTiming Comparison (ms):")
    print(
        f"  Profile 1: min={profile1.metadata.min_latency_ms:.1f}, "
        f"max={profile1.metadata.max_latency_ms:.1f}, "
        f"avg={profile1.metadata.avg_latency_ms:.1f}"
    )
    print(
        f"  Profile 2: min={profile2.metadata.min_latency_ms:.1f}, "
        f"max={profile2.metadata.max_latency_ms:.1f}, "
        f"avg={profile2.metadata.avg_latency_ms:.1f}"
    )

    return 0


def cmd_mock_test(args) -> int:
    """Test loading a profile into MockTransport."""
    try:
        from serialcables_sphinx import Sphinx
        from serialcables_sphinx.profiler import load_profile_to_mock
    except ImportError as e:
        print(f"Error importing modules: {e}", file=sys.stderr)
        return 1

    print(f"Loading profile: {args.profile}")

    try:
        mock = load_profile_to_mock(args.profile)
        sphinx = Sphinx(mock)

        print("\nTesting commands with loaded profile...")

        # Test health poll
        result = sphinx.nvme_mi.health_status_poll(eid=1)
        print(f"\nHealth Status Poll: {'SUCCESS' if result.success else 'FAILED'}")
        if result.success:
            print(f"  Temperature: {result.get('Composite Temperature', 'N/A')}")
            print(f"  Spare: {result.get('Available Spare', 'N/A')}")

        # Test subsystem info
        result = sphinx.nvme_mi.get_subsystem_info(eid=1)
        print(f"\nSubsystem Info: {'SUCCESS' if result.success else 'FAILED'}")
        if result.success:
            print(f"  NVMe-MI Version: {result.get('NVMe-MI Version', 'N/A')}")
            print(f"  Ports: {result.get('Number of Ports', 'N/A')}")

        # Test controller list
        result = sphinx.nvme_mi.get_controller_list(eid=1)
        print(f"\nController List: {'SUCCESS' if result.success else 'FAILED'}")
        if result.success:
            print(f"  Controllers: {result.get('Controller IDs', 'N/A')}")

        print("\n✓ Profile loaded successfully into MockTransport")
        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.debug:
            import traceback

            traceback.print_exc()
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="NVMe Device Profiler - Capture device responses for MockTransport",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Capture full profile from device
  %(prog)s --port COM13 --slot 1 --output samsung_990.json

  # Capture with custom name
  %(prog)s --port /dev/ttyUSB0 --slot 1 --name "Samsung 990 Pro 2TB"

  # Skip VPD capture (faster)
  %(prog)s --port COM13 --slot 1 --skip-vpd

  # View profile summary
  %(prog)s --load samsung_990.json --summary

  # Verify profile integrity
  %(prog)s --load samsung_990.json --verify

  # Compare two profiles
  %(prog)s --compare profile1.json profile2.json

  # Test profile in MockTransport
  %(prog)s --mock-test samsung_990.json
        """,
    )

    # Mode selection
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--load",
        metavar="FILE",
        help="Load and display profile from JSON file",
    )
    mode_group.add_argument(
        "--compare",
        nargs=2,
        metavar=("PROFILE1", "PROFILE2"),
        help="Compare two device profiles",
    )
    mode_group.add_argument(
        "--mock-test",
        metavar="FILE",
        help="Test loading profile into MockTransport",
    )

    # Capture options
    capture_group = parser.add_argument_group("Capture Options")
    capture_group.add_argument(
        "-p",
        "--port",
        help="Serial port for HYDRA (e.g., COM13, /dev/ttyUSB0)",
    )
    capture_group.add_argument(
        "-s",
        "--slot",
        type=int,
        default=1,
        help="Target slot number 1-8 (default: 1)",
    )
    capture_group.add_argument(
        "-e",
        "--eid",
        type=int,
        default=1,
        help="Target Endpoint ID (default: 1)",
    )
    capture_group.add_argument(
        "-n",
        "--name",
        help="Profile name (auto-generated if not specified)",
    )
    capture_group.add_argument(
        "-o",
        "--output",
        help="Output JSON file path",
    )
    capture_group.add_argument(
        "-t",
        "--timeout",
        type=float,
        default=3.0,
        help="Command timeout in seconds (default: 3.0)",
    )
    capture_group.add_argument(
        "-d",
        "--delay",
        type=float,
        default=50.0,
        help="Delay between commands in ms (default: 50)",
    )

    # Skip options
    skip_group = parser.add_argument_group("Skip Options")
    skip_group.add_argument("--skip-health", action="store_true", help="Skip health commands")
    skip_group.add_argument(
        "--skip-data-struct", action="store_true", help="Skip data structure commands"
    )
    skip_group.add_argument(
        "--skip-config", action="store_true", help="Skip configuration commands"
    )
    skip_group.add_argument("--skip-vpd", action="store_true", help="Skip VPD read")
    skip_group.add_argument(
        "--skip-admin", action="store_true", help="Skip admin tunneled commands"
    )

    # VPD options
    vpd_group = parser.add_argument_group("VPD Options")
    vpd_group.add_argument(
        "--vpd-max", type=int, default=4096, help="Max VPD offset to read (default: 4096)"
    )
    vpd_group.add_argument(
        "--vpd-chunk", type=int, default=256, help="VPD chunk size (default: 256)"
    )

    # Output options
    output_group = parser.add_argument_group("Output Options")
    output_group.add_argument(
        "--summary", action="store_true", help="Show profile summary (with --load)"
    )
    output_group.add_argument(
        "--verify", action="store_true", help="Verify profile checksum (with --load)"
    )
    output_group.add_argument(
        "--json", dest="json_output", action="store_true", help="Output as JSON (with --load)"
    )
    output_group.add_argument(
        "--compact", action="store_true", help="Compact JSON output (no indentation)"
    )
    output_group.add_argument(
        "-q", "--quiet", action="store_true", help="Quiet mode (minimal output)"
    )
    output_group.add_argument(
        "--debug", action="store_true", help="Show debug information on errors"
    )

    args = parser.parse_args()

    # Determine mode and run
    if args.load:
        return cmd_load(args)
    elif args.compare:
        args.profile1, args.profile2 = args.compare
        return cmd_compare(args)
    elif args.mock_test:
        args.profile = args.mock_test
        return cmd_mock_test(args)
    elif args.port:
        return cmd_capture(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
