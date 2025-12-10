#!/usr/bin/env python3
"""
sphinx-decode - CLI tool for decoding NVMe-MI packets.

Examples:
    # Decode a health status response
    sphinx-decode --opcode 0x01 "20 f 11 3b 1 0 0 c4 84 80 0 0 45"

    # Output as JSON
    sphinx-decode --opcode 0x01 --json "20 f 11 3b ..."

    # Decode with MCTP stripping
    sphinx-decode --opcode 0x01 --skip-mctp 8 "3a 0f 11 ..."
"""

import argparse
import json
import sys
from typing import Optional

from serialcables_sphinx.mctp.parser import MCTPParser
from serialcables_sphinx.nvme_mi.decoder import NVMeMIDecoder
from serialcables_sphinx.nvme_mi.opcodes import NVMeMIOpcode


def parse_opcode(value: str) -> int:
    """Parse opcode from string (supports hex and names)."""
    # Try as hex/int
    try:
        return int(value, 0)
    except ValueError:
        pass

    # Try as opcode name
    value_upper = value.upper().replace("-", "_")
    for op in NVMeMIOpcode:
        if op.name == value_upper:
            return op.value

    raise ValueError(f"Unknown opcode: {value}")


def main(args: Optional[list] = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Decode NVMe-MI responses",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Decode health status response (NVMe-MI payload only)
  %(prog)s --opcode 0x01 "00 00 00 00 01 25 00 45 10 50"

  # Decode with MCTP framing included
  %(prog)s --opcode 0x01 --mctp "20 f 11 3b 1 0 0 c4 84 00 00 00 01 25 00 45"

  # Output as JSON for scripting
  %(prog)s --opcode 0x01 --json "00 00 00 00 01 25 00 45"

  # Use opcode name instead of number
  %(prog)s --opcode NVM_SUBSYSTEM_HEALTH_STATUS_POLL "..."

  # Specify vendor ID for vendor-specific decoding
  %(prog)s --opcode 0xC0 --vendor 0x1234 "..."

Supported opcodes:
  0x00 / READ_NVME_MI_DATA_STRUCTURE
  0x01 / NVM_SUBSYSTEM_HEALTH_STATUS_POLL
  0x02 / CONTROLLER_HEALTH_STATUS_POLL
  0x03 / CONFIGURATION_SET
  0x04 / CONFIGURATION_GET
  0x05 / VPD_READ
  0x06 / VPD_WRITE
  0x07 / MI_RESET
  0xC0-0xFF / Vendor Specific
        """,
    )

    parser.add_argument(
        "packet",
        help="Hex packet bytes (space or comma separated)",
    )
    parser.add_argument(
        "-o",
        "--opcode",
        type=parse_opcode,
        default=0x01,
        help="NVMe-MI opcode (hex number or name, default: 0x01)",
    )
    parser.add_argument(
        "-t",
        "--data-type",
        type=lambda x: int(x, 0),
        help="Data structure type (for opcode 0x00)",
    )
    parser.add_argument(
        "-v",
        "--vendor",
        type=lambda x: int(x, 0),
        help="Vendor ID for vendor-specific decoding",
    )
    parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    parser.add_argument(
        "-m",
        "--mctp",
        action="store_true",
        help="Input includes MCTP framing (will be parsed)",
    )
    parser.add_argument(
        "-s",
        "--skip",
        type=int,
        default=0,
        help="Bytes to skip before NVMe-MI payload",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Show raw field data in output",
    )

    parsed = parser.parse_args(args)

    # Parse hex input
    try:
        hex_str = parsed.packet.replace(",", " ")
        parts = hex_str.split()
        raw_bytes = bytes(int(p, 16) for p in parts)
    except ValueError as e:
        print(f"Error parsing hex input: {e}", file=sys.stderr)
        return 1

    # Handle MCTP framing
    if parsed.mctp:
        try:
            mctp_parser = MCTPParser()
            mctp_parsed = mctp_parser.parse(raw_bytes, validate_pec=False)

            if not parsed.json:
                print(f"MCTP: {mctp_parsed}")
                print()

            # Extract NVMe-MI payload (message type byte + payload)
            nvme_mi_payload = bytes([mctp_parsed.msg_type]) + mctp_parsed.payload

            # For NVMe-MI response, we need to handle the response header
            # The MCTP payload should be: [Response Type][Status][Rsvd][Rsvd][Data...]
            raw_bytes = nvme_mi_payload[1:]  # Skip message type, decoder expects response format

        except Exception as e:
            print(f"Error parsing MCTP: {e}", file=sys.stderr)
            return 1
    elif parsed.skip > 0:
        raw_bytes = raw_bytes[parsed.skip :]

    # Decode
    decoder = NVMeMIDecoder(vendor_id=parsed.vendor)
    result = decoder.decode_response(
        raw_bytes,
        parsed.opcode,
        data_type=parsed.data_type,
    )

    # Output
    if parsed.json:
        output = result.to_dict()
        if parsed.raw:
            output["raw_input"] = parsed.packet
        print(json.dumps(output, indent=2, default=str))
    else:
        print(result.pretty_print())

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
