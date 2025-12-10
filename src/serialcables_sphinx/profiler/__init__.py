"""
Device Profiler - Capture real NVMe device responses for MockTransport.

This module provides tools to:
1. Profile a real NVMe device through HYDRA
2. Capture all read-only command responses
3. Save to JSON for MockTransport replay
4. Compare device behaviors across vendors

Usage:
    from serialcables_sphinx.profiler import DeviceProfiler, DeviceProfile

    # Capture from real device
    profiler = DeviceProfiler(port="COM13", slot=1)
    profile = profiler.capture_full_profile()
    profile.save("samsung_990_pro.json")

    # Load into MockTransport
    from serialcables_sphinx.transports.mock import MockTransport
    mock = MockTransport.from_profile("samsung_990_pro.json")
"""

from serialcables_sphinx.profiler.capture import CaptureConfig, DeviceProfiler
from serialcables_sphinx.profiler.loader import ProfileLoader, load_profile_to_mock
from serialcables_sphinx.profiler.profile import (
    CapturedCommand,
    DeviceProfile,
    ProfileMetadata,
)

__all__ = [
    "CaptureConfig",
    "DeviceProfiler",
    "DeviceProfile",
    "CapturedCommand",
    "ProfileMetadata",
    "ProfileLoader",
    "load_profile_to_mock",
]
