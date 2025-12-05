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

```python
from serialcables_hydra import HYDRADevice
from serialcables_sphinx import Sphinx

# Connect to HYDRA enclosure
hydra = HYDRADevice("/dev/ttyUSB0")

# Create Sphinx protocol handler
sphinx = Sphinx(hydra)

# Poll NVM Subsystem Health Status
result = sphinx.nvme_mi.health_status_poll(eid=1)

if result.success:
    print(result.pretty_print())
else:
    print(f"Error: {result.status}")
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
from serialcables_hydra import HYDRADevice
from serialcables_sphinx import Sphinx

@pytest.fixture
def sphinx():
    return Sphinx(HYDRADevice("/dev/ttyUSB0"))

def test_temperature_in_range(sphinx):
    result = sphinx.nvme_mi.health_status_poll(eid=1)
    assert result.success
    assert 0 <= result['Composite Temperature'] <= 70
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
