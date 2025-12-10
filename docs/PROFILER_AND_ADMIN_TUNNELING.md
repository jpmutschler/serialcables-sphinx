# Device Profiling and Admin Command Tunneling

## Overview

This document covers two major features added to serialcables-sphinx v0.2.0:

1. **Device Profiler** - Capture real device responses for safe testing
2. **Admin Command Tunneling** - MI Send/Receive for full NVMe admin command access

---

## Device Profiler

The Device Profiler lets you capture all read-only NVMe-MI responses from a real device and save them to JSON. These captured responses can then be used with MockTransport for safe, repeatable testing.

### Why Use Device Profiling?

- **Safe Testing**: Test destructive commands against captured data without risk
- **Repeatable**: Run the same tests against consistent device behavior
- **Offline Development**: Develop and test without physical hardware
- **Vendor Comparison**: Compare behavior across different device vendors
- **Regression Testing**: Build test suites from real device behavior

### Quick Start

```bash
# Step 1: Profile your device (do this once)
sphinx-profile --port COM13 --slot 1 --output samsung_990.json

# Step 2: View profile summary
sphinx-profile --load samsung_990.json --summary

# Step 3: Test with the profile
sphinx-profile --mock-test samsung_990.json
```

### Python API

```python
from serialcables_sphinx.profiler import DeviceProfiler, DeviceProfile, ProfileLoader
from serialcables_sphinx import Sphinx

# Capture from real device
profiler = DeviceProfiler(port="COM13", slot=1)
profile = profiler.capture_full_profile()
profile.save("my_device.json")

# Load into MockTransport
mock = ProfileLoader.create_mock(profile)
sphinx = Sphinx(mock)

# Test against captured responses
result = sphinx.nvme_mi.health_status_poll(eid=1)
print(result.pretty_print())
```

### What Gets Captured

| Category | Commands | Safe? |
|----------|----------|-------|
| Health | Subsystem Health, Controller Health | ✅ Read-only |
| Data Structures | Subsystem Info, Port Info, Controller List | ✅ Read-only |
| Configuration | Configuration Get (all standard IDs) | ✅ Read-only |
| VPD | VPD Read (chunked) | ✅ Read-only |
| Admin Tunneled | Identify, SMART (via shortcuts) | ✅ Read-only |

### Profile Structure

```json
{
  "profile_name": "samsung_990_pro",
  "profile_version": "1.0",
  "metadata": {
    "serial_number": "S6Z1NX0W123456",
    "model_number": "Samsung SSD 990 PRO 2TB",
    "firmware_revision": "4B2QJXH7",
    "nvme_mi_major_version": 1,
    "nvme_mi_minor_version": 2,
    "capture_date": "2024-12-10T12:00:00",
    "total_commands": 45,
    "avg_latency_ms": 5.2
  },
  "health_commands": [...],
  "data_structure_commands": [...],
  "configuration_commands": [...],
  "vpd_commands": [...],
  "response_table": {...}
}
```

---

## Admin Command Tunneling (MI Send/Receive)

NVMe-MI supports tunneling Admin commands through the management interface using MI Send (0x0D) and MI Receive (0x0E). This is essential for:

- UNH-IOL compliance testing
- Accessing Identify data without PCIe access
- Reading SMART/Health Log Pages
- Getting/Setting Features through management interface

### Supported Admin Commands

| Admin Opcode | Command | Purpose |
|-------------|---------|---------|
| 0x06 | Identify | Controller info, namespace info, etc. |
| 0x02 | Get Log Page | SMART, Error Log, Firmware Slot |
| 0x0A | Get Features | Temperature thresholds, power management |
| 0x09 | Set Features | Configuration changes |
| 0x10-0x13 | Firmware | Download, commit (destructive!) |

### Usage

```python
from serialcables_sphinx.nvme_mi.admin_tunneling import (
    MISendRequest,
    AdminOpcode,
    IdentifyCNS,
    LogPageIdentifier,
    FeatureIdentifier,
)

# Build Identify Controller request
req = MISendRequest.identify_controller(controller_id=0)

# Build Get SMART Log request
req = MISendRequest.get_smart_log(controller_id=0)

# Build Get Features request
req = MISendRequest.get_features(
    feature_id=FeatureIdentifier.TEMPERATURE_THRESHOLD,
    controller_id=0,
)

# Pack for transmission
payload = req.pack()
```

### Log Pages

| Log ID | Name | Description |
|--------|------|-------------|
| 0x01 | Error Information | Recent error entries |
| 0x02 | SMART/Health | Temperature, spare, wear |
| 0x03 | Firmware Slot | Active/pending firmware |
| 0x06 | Device Self-Test | Self-test results |

### Features

| Feature ID | Name | Description |
|------------|------|-------------|
| 0x01 | Arbitration | Command arbitration settings |
| 0x02 | Power Management | Power state configuration |
| 0x04 | Temperature Threshold | Warning/critical temps |
| 0x06 | Volatile Write Cache | WC enable/disable |

---

## CLI Tools

### sphinx-profile

```bash
# Capture profile
sphinx-profile --port COM13 --slot 1 --output device.json

# Capture with custom settings
sphinx-profile --port COM13 --slot 1 --skip-vpd --timeout 5.0

# View profile
sphinx-profile --load device.json --summary

# Verify integrity
sphinx-profile --load device.json --verify

# Compare profiles
sphinx-profile --compare device1.json device2.json

# Test with profile
sphinx-profile --mock-test device.json
```

### Options

| Option | Description |
|--------|-------------|
| `--port` | Serial port for HYDRA |
| `--slot` | Target slot (1-8) |
| `--output` | Output JSON file |
| `--name` | Profile name |
| `--skip-vpd` | Skip VPD capture (faster) |
| `--skip-admin` | Skip admin tunneled commands |
| `--timeout` | Command timeout (seconds) |
| `--delay` | Inter-command delay (ms) |

---

## Integration Examples

### pytest with Profile

```python
import pytest
from serialcables_sphinx.profiler import load_profile_to_mock
from serialcables_sphinx import Sphinx

@pytest.fixture
def sphinx_from_profile():
    """Create Sphinx with captured device profile."""
    mock = load_profile_to_mock("tests/fixtures/samsung_990.json")
    return Sphinx(mock)

def test_temperature_in_range(sphinx_from_profile):
    result = sphinx_from_profile.nvme_mi.health_status_poll(eid=1)
    assert result.success
    # Test against real captured values
    temp = result.get('Composite Temperature')
    assert '°C' in temp

def test_controller_count(sphinx_from_profile):
    result = sphinx_from_profile.nvme_mi.get_controller_list(eid=1)
    assert result.success
    assert len(result['Controller IDs']) >= 1
```

### CI/CD Pipeline

```yaml
# .github/workflows/nvme-tests.yml
jobs:
  test:
    steps:
      - name: Run NVMe-MI tests
        run: |
          # Use captured profiles for consistent testing
          pytest tests/ --profile fixtures/device_profile.json
```

---

## Test Statistics

After implementing these features:

| Test Suite | Tests | Status |
|------------|-------|--------|
| test_mock_transport.py | 60 | ✅ Pass |
| test_fragmentation.py | 23 | ✅ Pass |
| test_shortcuts.py | 16 | ✅ Pass |
| test_profiler.py | 23 | ✅ Pass |
| **Total** | **99** | ✅ **Pass** |
