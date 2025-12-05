# serialcables-sphinx

MCTP and NVMe-MI protocol library for Serial Cables HYDRA enclosures.

**Sphinx** handles the protocol layer (MCTP framing, NVMe-MI encoding/decoding) while **HYDRA** handles the transport layer (serial communication with hardware). Together they provide a complete end-to-end solution for NVMe Management Interface communication.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              Host Application                               │
│    (Prometheus UI, LabView, pytest, Jenkins, scripts)       │
├─────────────────────────────────────────────────────────────┤
│                  serialcables-sphinx                        │
│    • MCTP packet building        • NVMe-MI decoding         │
│    • NVMe-MI request encoding    • Human-readable output    │
├─────────────────────────────────────────────────────────────┤
│                  serialcables-hydra                         │
│    • Serial communication        • Slot/mux management      │
│    • Raw packet transport        • Device enumeration       │
├─────────────────────────────────────────────────────────────┤
│                  HYDRA Hardware                             │
│    • MCU + Serial Mux            • I2C/SMBus to DUTs       │
└─────────────────────────────────────────────────────────────┘
```

## Installation

```bash
pip install serialcables-sphinx
```

This automatically installs `serialcables-hydra` as a dependency.

## Quick Start

### With Real HYDRA Hardware

```python
from serialcables_hydra import JBOFController
from serialcables_sphinx import Sphinx
from serialcables_sphinx.transports.hydra import HYDRATransport

# Connect to HYDRA enclosure
jbof = JBOFController()
jbof.connect("/dev/ttyUSB0")  # or "COM3" on Windows

# Create transport adapter for slot 1
transport = HYDRATransport(jbof, slot=1)

# Create Sphinx protocol handler
sphinx = Sphinx(transport)

# Poll NVM Subsystem Health Status
result = sphinx.nvme_mi.health_status_poll(eid=1)

if result.success:
    print(result.pretty_print())
else:
    print(f"Error: {result.status}")
```

### With Mock Transport (Testing)

```python
from serialcables_sphinx import Sphinx
from serialcables_sphinx.transports.mock import MockTransport

# Create mock transport (no hardware needed)
mock = MockTransport()

# Optionally configure simulated device state
mock.set_temperature(45)  # 45°C
mock.state.available_spare = 90

# Use identically to real hardware
sphinx = Sphinx(mock)
result = sphinx.nvme_mi.health_status_poll(eid=1)
print(result.pretty_print())
```

## Features

### High-Level API

Simple methods for common NVMe-MI operations:

```python
# Health monitoring
health = sphinx.nvme_mi.health_status_poll(eid=1)
print(f"Temperature: {health['Composite Temperature']}")
print(f"Spare: {health['Available Spare']}")

# Controller enumeration
controllers = sphinx.nvme_mi.get_controller_list(eid=1)
for ctrl_id in controllers['Controller IDs']:
    ctrl_health = sphinx.nvme_mi.controller_health_status(eid=1, controller_id=ctrl_id)
    print(ctrl_health.pretty_print())

# Subsystem information
info = sphinx.nvme_mi.get_subsystem_info(eid=1)
print(f"NVMe-MI Version: {info['NVMe-MI Version']}")
```

### Mid-Level API

Build and decode packets explicitly (useful for debugging):

```python
from serialcables_sphinx import NVMeMIOpcode

# Build packet
packet = sphinx.mctp.build_nvme_mi_request(
    dest_eid=1,
    opcode=NVMeMIOpcode.NVM_SUBSYSTEM_HEALTH_STATUS_POLL
)
print(f"TX: {packet.hex(' ')}")

# Send raw bytes via HYDRA
response_bytes = hydra.send_packet(packet)
print(f"RX: {response_bytes.hex(' ')}")

# Decode response
decoded = sphinx.nvme_mi.decode(
    response_bytes, 
    NVMeMIOpcode.NVM_SUBSYSTEM_HEALTH_STATUS_POLL
)
print(decoded.pretty_print())
```

### Low-Level API

Full control over MCTP framing:

```python
# Build custom MCTP packet
packet = sphinx.mctp.build_raw(
    dest_eid=1,
    src_eid=0,
    msg_type=0x04,  # NVMe-MI
    payload=bytes([0x01, 0x00, 0x00, 0x00]),
    som=True,
    eom=True
)
```

### Message Fragmentation

The library handles MCTP message fragmentation for payloads exceeding packet size limits:

```python
from serialcables_sphinx.mctp import (
    MCTPBuilder,
    FragmentationConstants,
    FragmentedMessage,
)

# Hardware constraints
print(f"Max TX packet: {FragmentationConstants.MAX_TX_PACKET_SIZE} bytes")  # 128
print(f"Max RX packet: {FragmentationConstants.MAX_RX_PACKET_SIZE} bytes")  # 256
print(f"Max TX payload: {FragmentationConstants.MAX_TX_PAYLOAD} bytes")     # 120

# Check if fragmentation needed
builder = MCTPBuilder()
large_payload = bytes(300)
print(f"Needs fragmentation: {builder.needs_fragmentation(large_payload)}")
print(f"Fragment count: {builder.calculate_fragment_count(large_payload)}")

# Build fragmented message
result = builder.build_fragmented(
    dest_eid=1,
    msg_type=0x04,
    payload=large_payload,
)

# Send with timing control
for fragment in result.fragments:
    transport.send_packet(fragment.data)
    time.sleep(0.005)  # 5ms inter-fragment delay
```

Fragmentation parameters:
- **TX limit**: 128 bytes per packet (hardware constraint)
- **RX limit**: 256 bytes per packet (MCU memory constraint)  
- **Timing**: Fragments must arrive within ~100ms for device reassembly
- **Sequence**: 2-bit counter (0-3) wraps for messages > 4 fragments

### Output Formats

```python
# Human-readable (for debugging)
print(result.pretty_print())

# Dictionary (for JSON APIs)
data = result.to_dict()

# Direct field access
temp = result['Composite Temperature']
spare = result.get('Available Spare', 'N/A')

# One-line summary
print(result.summary())  # "[✓] NVM_SUBSYSTEM_HEALTH_STATUS_POLL: SUCCESS (0x00)"
```

### CLI Tool

Decode packets from the command line:

```bash
# Decode a captured response
sphinx-decode --opcode 0x01 "20 f 11 3b 1 0 0 c4 84 80 0 0 45 0 0 ca 1e a0 90 a0"

# Output as JSON
sphinx-decode --opcode 0x01 --json "20 f 11 3b ..."
```

## Supported NVMe-MI Commands

| Opcode | Command | Decode Support |
|--------|---------|----------------|
| 0x00 | Read NVMe-MI Data Structure | ✓ |
| 0x01 | NVM Subsystem Health Status Poll | ✓ |
| 0x02 | Controller Health Status Poll | ✓ |
| 0x03 | Configuration Set | ✓ |
| 0x04 | Configuration Get | ✓ |
| 0x05 | VPD Read | ✓ |
| 0x06 | VPD Write | ✓ |
| 0x07 | MI Reset | ✓ |
| 0x08 | SES Receive | Planned |
| 0x09 | SES Send | Planned |
| 0xC0+ | Vendor Specific | Extensible |

## Vendor Extensions

Register custom decoders for vendor-specific commands:

```python
from serialcables_sphinx import DecoderRegistry, ResponseDecoder

@DecoderRegistry.register(opcode=0xC0, vendor_id=0x1234)
class MyVendorDecoder(ResponseDecoder):
    def decode(self, data: bytes, response):
        self._add_field(response, "Custom Field", data[0], data[0:1])
        return response

# Use with vendor ID
sphinx = Sphinx(hydra, vendor_id=0x1234)
```

## Integration Examples

### pytest

```python
import pytest
from serialcables_sphinx import Sphinx
from serialcables_sphinx.transports.mock import MockTransport

# For unit tests, use mock transport
@pytest.fixture
def sphinx():
    mock = MockTransport()
    return Sphinx(mock)

def test_temperature_in_range(sphinx):
    result = sphinx.nvme_mi.health_status_poll(eid=1)
    assert result.success
    # Check decoded temperature field
    temp_str = result['Composite Temperature']
    assert "°C" in temp_str

# For hardware integration tests
@pytest.fixture
def sphinx_hardware():
    from serialcables_sphinx.transports.hydra import create_hydra_transport
    transport = create_hydra_transport("/dev/ttyUSB0", slot=1)
    return Sphinx(transport)
```

### LabView

Use Python Node to import and call Sphinx methods, returning dict/JSON to LabView.

### Jenkins Pipeline

```groovy
stage('NVMe-MI Health Check') {
    steps {
        sh '''
            python -c "
from serialcables_hydra import HYDRADevice
from serialcables_sphinx import Sphinx
sphinx = Sphinx(HYDRADevice('/dev/ttyUSB0'))
result = sphinx.nvme_mi.health_status_poll(eid=1)
assert result.success, f'Health check failed: {result.status}'
print(result.pretty_print())
"
        '''
    }
}
```

## Requirements

- Python 3.9+
- serialcables-hydra >= 0.1.0

## License

MIT License - see LICENSE file for details.

## Links

- [Serial Cables](https://serialcables.com)
- [HYDRA Documentation](https://github.com/serialcables/serialcables-hydra)
- [NVMe-MI Specification](https://nvmexpress.org/specifications/)
- [MCTP Specification (DMTF DSP0236)](https://www.dmtf.org/standards/pmci)
