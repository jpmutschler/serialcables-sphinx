#!/usr/bin/env python3
"""
Basic usage example demonstrating Sphinx with mock transport.

This example shows:
- Creating a Sphinx client with mock transport
- Polling health status
- Reading subsystem information
- Accessing decoded fields
- Using different output formats

Run from project root:
    python -m examples.basic_usage
"""

from serialcables_sphinx import Sphinx
from serialcables_sphinx.transports.mock import MockTransport


def main():
    # Create mock transport (simulates HYDRA device)
    mock = MockTransport(verbose=True)
    
    # Optionally configure simulated device state
    mock.set_temperature(42)  # 42°C
    mock.state.available_spare = 95
    mock.state.life_used = 3
    
    # Create Sphinx client
    sphinx = Sphinx(mock)
    
    print("=" * 60)
    print("SPHINX BASIC USAGE EXAMPLE")
    print("=" * 60)
    
    # -------------------------------------------------------------------------
    # Health Status Poll
    # -------------------------------------------------------------------------
    print("\n--- Health Status Poll ---")
    
    result = sphinx.nvme_mi.health_status_poll(eid=1)
    
    # Check success
    if result.success:
        print("\n✓ Health poll successful!")
        
        # Access individual fields
        print(f"\nKey metrics:")
        print(f"  Temperature: {result['Composite Temperature']}")
        print(f"  Available Spare: {result['Available Spare']}")
        print(f"  Drive Life Used: {result['Drive Life Used']}")
        print(f"  Ready: {result['Ready (RDY)']}")
        
        # Safe access with default
        warning = result.get('Critical Warning', 'N/A')
        print(f"  Critical Warning: {warning}")
        
    else:
        print(f"✗ Health poll failed: {result.status}")
    
    # Pretty print full response
    print("\n--- Full Response (pretty print) ---")
    print(result.pretty_print())
    
    # One-line summary
    print(f"Summary: {result.summary()}")
    
    # -------------------------------------------------------------------------
    # Subsystem Information
    # -------------------------------------------------------------------------
    print("\n--- Subsystem Information ---")
    
    info = sphinx.nvme_mi.get_subsystem_info(eid=1)
    
    if info.success:
        print(f"NVMe-MI Version: {info['NVMe-MI Version']}")
        print(f"Number of Ports: {info['Number of Ports']}")
        print(f"Optional Commands: {info['Optional Commands Supported']}")
    
    # -------------------------------------------------------------------------
    # Controller List
    # -------------------------------------------------------------------------
    print("\n--- Controller List ---")
    
    ctrl_list = sphinx.nvme_mi.get_controller_list(eid=1)
    
    if ctrl_list.success:
        controller_ids = ctrl_list['Controller IDs']
        print(f"Found {len(controller_ids)} controller(s): {controller_ids}")
        
        # Poll each controller
        for ctrl_id in controller_ids:
            ctrl_health = sphinx.nvme_mi.controller_health_status(ctrl_id, eid=1)
            if ctrl_health.success:
                print(f"\n  Controller {ctrl_id}:")
                print(f"    Ready: {ctrl_health['Controller Ready']}")
                print(f"    Temperature: {ctrl_health['Composite Temperature']}")
    
    # -------------------------------------------------------------------------
    # Export to Dictionary (for JSON APIs)
    # -------------------------------------------------------------------------
    print("\n--- Export to Dict ---")
    
    data = result.to_dict()
    print(f"Keys: {list(data.keys())}")
    print(f"Success: {data['success']}")
    print(f"Field count: {len(data['fields'])}")
    
    # Flat dict (just values)
    flat = result.to_flat_dict()
    print(f"\nFlat dict sample: temperature={flat.get('Composite Temperature')}")
    
    # -------------------------------------------------------------------------
    # Packet Inspection
    # -------------------------------------------------------------------------
    print("\n--- Packet Inspection ---")
    print(f"Total packets sent: {len(mock.sent_packets)}")
    print(f"Last request: {mock.get_last_request().hex(' ')}")
    print(f"Last opcode: 0x{mock.get_last_opcode():02X}")
    
    print("\n" + "=" * 60)
    print("Example complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
