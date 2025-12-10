#!/usr/bin/env python3
"""
Example: Device Profiling for Safe Testing

This example demonstrates the complete workflow for:
1. Profiling a real NVMe device
2. Saving the profile to JSON
3. Loading the profile into MockTransport
4. Testing against the captured responses

This approach lets you:
- Run comprehensive tests without risk to the device
- Test destructive commands against captured data
- Compare behavior across different device vendors
- Build regression test suites from real device behavior

Usage:
    # Step 1: Profile a real device (do this once)
    python -m examples.device_profiling --port COM13 --capture
    
    # Step 2: Test against the profile (safe, repeatable)
    python -m examples.device_profiling --profile my_device.json --test
    
    # Step 3: Compare profiles
    python -m examples.device_profiling --compare profile1.json profile2.json
"""

import argparse
import sys
import os

# Add src to path for development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def demonstrate_capture(port: str, slot: int, output: str) -> int:
    """Demonstrate capturing a device profile."""
    from serialcables_sphinx.profiler import DeviceProfiler, CaptureConfig
    
    print("=" * 60)
    print("DEVICE PROFILE CAPTURE")
    print("=" * 60)
    print(f"Port: {port}")
    print(f"Slot: {slot}")
    print(f"Output: {output}")
    print()
    print("This will capture all read-only NVMe-MI commands from")
    print("the device. The captured responses will be saved to")
    print("JSON for use with MockTransport.")
    print()
    print("Press Ctrl+C at any time to abort.")
    print("=" * 60)
    
    # Configure capture
    config = CaptureConfig(
        capture_health=True,
        capture_data_structures=True,
        capture_configuration=True,
        capture_vpd=True,
        capture_admin_tunneled=True,
        command_delay_ms=50.0,
        timeout=3.0,
        verbose=True,
    )
    
    try:
        # Create profiler
        profiler = DeviceProfiler(
            port=port,
            slot=slot,
            config=config,
        )
        
        # Capture profile
        profile = profiler.capture_full_profile()
        
        # Save to file
        profile.save(output)
        
        print()
        print("=" * 60)
        print("CAPTURE COMPLETE")
        print("=" * 60)
        print(profile.summary())
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\nCapture interrupted by user")
        return 1
    except Exception as e:
        print(f"\nError: {e}")
        return 1


def demonstrate_testing(profile_path: str) -> int:
    """Demonstrate testing against a captured profile."""
    from serialcables_sphinx.profiler import DeviceProfile, ProfileLoader
    from serialcables_sphinx import Sphinx
    
    print("=" * 60)
    print("TESTING WITH CAPTURED PROFILE")
    print("=" * 60)
    print(f"Profile: {profile_path}")
    print()
    
    # Load profile
    print("Loading profile...")
    profile = DeviceProfile.load(profile_path)
    
    print(f"Device: {profile.metadata.model_number or 'Unknown'}")
    print(f"Serial: {profile.metadata.serial_number or 'Unknown'}")
    print(f"Commands captured: {len(profile.get_all_commands())}")
    print()
    
    # Create mock from profile
    print("Creating MockTransport from profile...")
    mock = ProfileLoader.create_mock(profile)
    sphinx = Sphinx(mock)
    
    print()
    print("-" * 60)
    print("Running test commands against captured responses:")
    print("-" * 60)
    
    # Test each command type
    tests = [
        ("Health Status Poll", lambda: sphinx.nvme_mi.health_status_poll(eid=1)),
        ("Subsystem Info", lambda: sphinx.nvme_mi.get_subsystem_info(eid=1)),
        ("Controller List", lambda: sphinx.nvme_mi.get_controller_list(eid=1)),
        ("Port Info", lambda: sphinx.nvme_mi.get_port_info(port_id=0, eid=1)),
        ("VPD Read", lambda: sphinx.nvme_mi.vpd_read(offset=0, length=64, eid=1)),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            result = test_func()
            status = "✓ PASS" if result.success else "✗ FAIL"
            if result.success:
                passed += 1
            else:
                failed += 1
            print(f"  {name}: {status}")
            
            # Show some details
            if result.success and result.fields:
                for field_name, field in list(result.fields.items())[:2]:
                    print(f"      {field_name}: {field.value}")
                    
        except Exception as e:
            failed += 1
            print(f"  {name}: ✗ ERROR - {e}")
    
    print()
    print("-" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("-" * 60)
    
    # Verify timing matches
    print()
    print("Profile Timing Statistics:")
    print(f"  Min latency: {profile.metadata.min_latency_ms:.2f} ms")
    print(f"  Max latency: {profile.metadata.max_latency_ms:.2f} ms")
    print(f"  Avg latency: {profile.metadata.avg_latency_ms:.2f} ms")
    
    return 0 if failed == 0 else 1


def demonstrate_comparison(profile1_path: str, profile2_path: str) -> int:
    """Compare two device profiles."""
    from serialcables_sphinx.profiler import DeviceProfile
    
    print("=" * 60)
    print("DEVICE PROFILE COMPARISON")
    print("=" * 60)
    
    # Load profiles
    print(f"\nLoading {profile1_path}...")
    profile1 = DeviceProfile.load(profile1_path)
    
    print(f"Loading {profile2_path}...")
    profile2 = DeviceProfile.load(profile2_path)
    
    print()
    print("-" * 60)
    print("Device Information")
    print("-" * 60)
    
    print(f"\nProfile 1: {profile1.profile_name}")
    print(f"  Model: {profile1.metadata.model_number or 'Unknown'}")
    print(f"  Serial: {profile1.metadata.serial_number or 'Unknown'}")
    print(f"  Firmware: {profile1.metadata.firmware_revision or 'Unknown'}")
    print(f"  NVMe-MI: {profile1.metadata.nvme_mi_major_version}.{profile1.metadata.nvme_mi_minor_version}")
    
    print(f"\nProfile 2: {profile2.profile_name}")
    print(f"  Model: {profile2.metadata.model_number or 'Unknown'}")
    print(f"  Serial: {profile2.metadata.serial_number or 'Unknown'}")
    print(f"  Firmware: {profile2.metadata.firmware_revision or 'Unknown'}")
    print(f"  NVMe-MI: {profile2.metadata.nvme_mi_major_version}.{profile2.metadata.nvme_mi_minor_version}")
    
    print()
    print("-" * 60)
    print("Command Support Comparison")
    print("-" * 60)
    
    # Get successful commands
    def get_cmd_signatures(profile):
        return {
            (c.opcode, c.data_type, c.config_id): c
            for c in profile.get_all_commands()
            if c.success
        }
    
    cmds1 = get_cmd_signatures(profile1)
    cmds2 = get_cmd_signatures(profile2)
    
    common = set(cmds1.keys()) & set(cmds2.keys())
    only1 = set(cmds1.keys()) - set(cmds2.keys())
    only2 = set(cmds2.keys()) - set(cmds1.keys())
    
    print(f"\nCommon commands: {len(common)}")
    print(f"Only in Profile 1: {len(only1)}")
    print(f"Only in Profile 2: {len(only2)}")
    
    if only1:
        print("\n  Commands only in Profile 1:")
        for key in sorted(only1):
            opcode, dt, cfg = key
            cmd = cmds1[key]
            print(f"    - {cmd.opcode_name} (0x{opcode:02X})")
    
    if only2:
        print("\n  Commands only in Profile 2:")
        for key in sorted(only2):
            opcode, dt, cfg = key
            cmd = cmds2[key]
            print(f"    - {cmd.opcode_name} (0x{opcode:02X})")
    
    print()
    print("-" * 60)
    print("Response Time Comparison")
    print("-" * 60)
    
    print(f"\n{'Command':<35} {'Profile 1':>12} {'Profile 2':>12} {'Diff':>12}")
    print("-" * 71)
    
    for key in sorted(common):
        cmd1 = cmds1[key]
        cmd2 = cmds2[key]
        diff = cmd2.latency_ms - cmd1.latency_ms
        diff_str = f"+{diff:.1f}" if diff >= 0 else f"{diff:.1f}"
        print(f"{cmd1.opcode_name:<35} {cmd1.latency_ms:>10.1f}ms {cmd2.latency_ms:>10.1f}ms {diff_str:>10}ms")
    
    return 0


def demonstrate_mock_integration() -> int:
    """Show how MockTransport uses profiles internally."""
    from serialcables_sphinx.transports.mock import MockTransport, MockDeviceState
    from serialcables_sphinx import Sphinx
    
    print("=" * 60)
    print("MOCK TRANSPORT DEMONSTRATION")
    print("=" * 60)
    print()
    print("This shows how MockTransport can be configured with")
    print("custom state to simulate different device conditions.")
    print()
    
    # Create mock with custom state
    state = MockDeviceState(
        temperature_kelvin=358,  # 85°C - hot!
        available_spare=5,  # Very low
        spare_threshold=10,
        life_used=95,  # Nearly worn out
        critical_warning=0x03,  # Temperature + spare warning
    )
    
    mock = MockTransport(state=state)
    sphinx = Sphinx(mock)
    
    print("Simulated device state:")
    print(f"  Temperature: {state.temperature_kelvin - 273}°C (critical!)")
    print(f"  Available Spare: {state.available_spare}% (below threshold)")
    print(f"  Life Used: {state.life_used}%")
    print(f"  Critical Warning: 0x{state.critical_warning:02X}")
    print()
    
    # Query the mock device
    result = sphinx.nvme_mi.health_status_poll(eid=1)
    
    print("Query Result:")
    print(result.pretty_print())
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Device profiling demonstration",
    )
    
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--capture",
        action="store_true",
        help="Capture profile from real device",
    )
    mode.add_argument(
        "--test",
        action="store_true",
        help="Test against captured profile",
    )
    mode.add_argument(
        "--compare",
        nargs=2,
        metavar=("PROFILE1", "PROFILE2"),
        help="Compare two profiles",
    )
    mode.add_argument(
        "--mock-demo",
        action="store_true",
        help="Demonstrate MockTransport without hardware",
    )
    
    parser.add_argument(
        "-p", "--port",
        help="Serial port for capture (e.g., COM13)",
    )
    parser.add_argument(
        "-s", "--slot",
        type=int,
        default=1,
        help="Target slot (default: 1)",
    )
    parser.add_argument(
        "--profile",
        help="Profile JSON file for testing",
    )
    parser.add_argument(
        "-o", "--output",
        default="device_profile.json",
        help="Output file for capture (default: device_profile.json)",
    )
    
    args = parser.parse_args()
    
    if args.capture:
        if not args.port:
            print("Error: --port required for capture mode")
            return 1
        return demonstrate_capture(args.port, args.slot, args.output)
    
    elif args.test:
        if not args.profile:
            print("Error: --profile required for test mode")
            return 1
        return demonstrate_testing(args.profile)
    
    elif args.compare:
        return demonstrate_comparison(args.compare[0], args.compare[1])
    
    elif args.mock_demo:
        return demonstrate_mock_integration()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
