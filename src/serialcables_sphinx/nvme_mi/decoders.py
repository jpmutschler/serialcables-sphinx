"""
NVMe-MI response decoder implementations.

Each decoder handles a specific NVMe-MI opcode and extracts
human-readable fields from the response data.

Supports NVMe-MI 1.2 and 2.x response formats.
"""

from __future__ import annotations

import struct

from serialcables_sphinx.nvme_mi.base_decoder import ResponseDecoder
from serialcables_sphinx.nvme_mi.constants import (
    CriticalWarningFlags,
    EnduranceGroupCriticalWarning,
    NVMeDataStructureType,
    ShutdownStatus,
)
from serialcables_sphinx.nvme_mi.opcodes import NVMeMIOpcode
from serialcables_sphinx.nvme_mi.registry import DecoderRegistry
from serialcables_sphinx.nvme_mi.response import DecodedResponse


@DecoderRegistry.register(opcode=NVMeMIOpcode.NVM_SUBSYSTEM_HEALTH_STATUS_POLL)
class HealthStatusPollDecoder(ResponseDecoder):
    """
    Decoder for NVM Subsystem Health Status Poll (Opcode 0x01).

    Supports both NVMe-MI 1.2 (20-byte response) and NVMe-MI 2.x (32-byte response).

    Reference:
        - NVMe-MI 1.2, Section 6.2
        - NVMe-MI 2.0, Section 6.2 (extended format)
    """

    # Response size thresholds
    NVME_MI_1X_RESPONSE_SIZE = 20
    NVME_MI_2X_RESPONSE_SIZE = 32

    def decode(self, data: bytes, response: DecodedResponse) -> DecodedResponse:
        if len(data) < 1:
            response.decode_errors.append(f"Health status response too short: {len(data)} bytes")
            return response

        # Detect NVMe-MI version based on response size
        is_2x_response = len(data) >= self.NVME_MI_2X_RESPONSE_SIZE
        if is_2x_response:
            self._add_field(response, "Response Format", "NVMe-MI 2.x (extended)", data[0:1])
        else:
            self._add_field(response, "Response Format", "NVMe-MI 1.x", data[0:1])

        # Byte 0: Composite Controller Status (CCS)
        ccs = data[0]
        self._add_field(response, "Composite Controller Status", f"0x{ccs:02X}", data[0:1])

        # Decode CCS bits
        rdy = bool(ccs & 0x01)
        cfs = bool(ccs & 0x02)
        shst = (ccs >> 2) & 0x03
        nssro = bool(ccs & 0x10)
        ceco = bool(ccs & 0x20)
        nace = bool(ccs & 0x40)

        self._add_field(
            response,
            "Ready (RDY)",
            rdy,
            data[0:1],
            description="Controller ready to process commands" if rdy else "Controller not ready",
        )
        self._add_field(
            response,
            "Controller Fatal Status (CFS)",
            cfs,
            data[0:1],
            description="Fatal controller condition detected" if cfs else "No fatal condition",
        )
        self._add_field(response, "Shutdown Status (SHST)", str(ShutdownStatus(shst)), data[0:1])
        self._add_field(response, "NVM Subsystem Reset Occurred", nssro, data[0:1])
        self._add_field(response, "Controller Enable Change Occurred", ceco, data[0:1])
        self._add_field(response, "Namespace Attribute Changed", nace, data[0:1])

        # Byte 1: Critical Warnings
        if len(data) > 1:
            cw = CriticalWarningFlags(data[1])
            self._add_field(
                response, "Critical Warning", f"0x{data[1]:02X}", data[1:2], description=str(cw)
            )

        # Bytes 2-3: Composite Temperature (Kelvin)
        if len(data) >= 4:
            (temp_k,) = struct.unpack("<H", data[2:4])
            temp_str, _ = self._decode_temperature(temp_k)
            self._add_field(response, "Composite Temperature", temp_str, data[2:4])
        elif len(data) > 2:
            # Single byte temperature (older devices)
            temp_k = data[2]
            temp_str, _ = self._decode_temperature(temp_k)
            self._add_field(response, "Composite Temperature", temp_str, data[2:3])

        # Byte 4: Percentage Drive Life Used
        if len(data) > 4:
            life_used = data[4]
            life_str = self._decode_percentage(life_used)
            desc = ""
            if life_used != 255 and life_used >= 100:
                desc = "Exceeded rated endurance"
            self._add_field(response, "Drive Life Used", life_str, data[4:5], description=desc)

        # Byte 5: Available Spare Threshold
        if len(data) > 5:
            spare_thresh = data[5]
            self._add_field(
                response,
                "Available Spare Threshold",
                self._decode_percentage(spare_thresh),
                data[5:6],
            )

        # Byte 6: Available Spare
        if len(data) > 6:
            spare = data[6]
            spare_str = self._decode_percentage(spare)
            desc = ""
            if len(data) > 5 and spare != 255 and data[5] != 255:
                if spare < data[5]:
                    desc = "Below threshold!"
            self._add_field(response, "Available Spare", spare_str, data[6:7], description=desc)

        # =====================================================================
        # NVMe-MI 2.x Extended Fields (bytes 20-31)
        # =====================================================================
        if is_2x_response:
            # Bytes 20-23: Endurance Group Critical Warning Summary
            if len(data) >= 24:
                (egcws,) = struct.unpack("<I", data[20:24])
                eg_warnings = EnduranceGroupCriticalWarning(egcws & 0xFF)
                self._add_field(
                    response,
                    "Endurance Group Critical Warning",
                    f"0x{egcws:08X}",
                    data[20:24],
                    description=", ".join(eg_warnings.decode()),
                )

            # Bytes 24-27: Reserved in 2.0, may have data in 2.1+
            # Bytes 28-31: Vendor Specific
            if len(data) >= 32:
                vendor_data = data[28:32]
                if any(b != 0 for b in vendor_data):
                    self._add_field(
                        response,
                        "Vendor Specific Data",
                        vendor_data.hex(),
                        vendor_data,
                    )

        return response


@DecoderRegistry.register(opcode=NVMeMIOpcode.CONTROLLER_HEALTH_STATUS_POLL)
class ControllerHealthStatusDecoder(ResponseDecoder):
    """
    Decoder for Controller Health Status Poll (Opcode 0x02).

    Supports both NVMe-MI 1.2 (16-byte response) and NVMe-MI 2.x (32-byte response).

    Reference:
        - NVMe-MI 1.2, Section 6.3
        - NVMe-MI 2.0, Section 6.3 (extended format)
    """

    # Response size thresholds
    NVME_MI_1X_RESPONSE_SIZE = 16
    NVME_MI_2X_RESPONSE_SIZE = 32

    def decode(self, data: bytes, response: DecodedResponse) -> DecodedResponse:
        if len(data) < 8:
            response.decode_errors.append(
                f"Controller health response too short: {len(data)} bytes"
            )
            return response

        # Detect NVMe-MI version based on response size
        is_2x_response = len(data) >= self.NVME_MI_2X_RESPONSE_SIZE
        if is_2x_response:
            self._add_field(response, "Response Format", "NVMe-MI 2.x (extended)", data[0:1])

        # Bytes 0-1: Controller ID
        (ctrlr_id,) = self._safe_unpack("<H", data, 0, response)
        self._add_field(response, "Controller ID", ctrlr_id, data[0:2])

        # Byte 2: Controller Status
        csts = data[2]
        rdy = bool(csts & 0x01)
        cfs = bool(csts & 0x02)
        shst = (csts >> 2) & 0x03

        self._add_field(response, "Controller Ready", rdy, data[2:3])
        self._add_field(response, "Controller Fatal Status", cfs, data[2:3])
        self._add_field(response, "Shutdown Status", str(ShutdownStatus(shst)), data[2:3])

        # Bytes 4-5: Composite Temperature
        if len(data) >= 6:
            (temp_k,) = self._safe_unpack("<H", data, 4, response)
            if temp_k != 0:
                temp_str, _ = self._decode_temperature(temp_k)
                self._add_field(response, "Composite Temperature", temp_str, data[4:6])

        # Bytes 6-7: Warning Composite Temp Threshold
        if len(data) >= 8:
            (wctemp,) = self._safe_unpack("<H", data, 6, response)
            if wctemp != 0:
                temp_str, _ = self._decode_temperature(wctemp)
                self._add_field(response, "Warning Temp Threshold", temp_str, data[6:8])

        # Bytes 8-9: Critical Composite Temp Threshold
        if len(data) >= 10:
            (cctemp,) = self._safe_unpack("<H", data, 8, response)
            if cctemp != 0:
                temp_str, _ = self._decode_temperature(cctemp)
                self._add_field(response, "Critical Temp Threshold", temp_str, data[8:10])

        # Bytes 10-11: Available Spare / Threshold
        if len(data) >= 12:
            spare = data[10]
            thresh = data[11]
            self._add_field(
                response, "Available Spare", self._decode_percentage(spare), data[10:11]
            )
            self._add_field(
                response, "Spare Threshold", self._decode_percentage(thresh), data[11:12]
            )

        # Byte 12: Percentage Used
        if len(data) > 12:
            pct_used = data[12]
            pct_str = self._decode_percentage(pct_used)
            desc = ""
            if pct_used != 255 and pct_used >= 100:
                desc = "Exceeded rated endurance"
            self._add_field(response, "Percentage Used", pct_str, data[12:13], description=desc)

        # =====================================================================
        # NVMe-MI 2.x Extended Fields (bytes 16-31)
        # =====================================================================
        if is_2x_response:
            # Bytes 16-17: Controller Temperature Sensor 1
            if len(data) >= 18:
                (cts1,) = self._safe_unpack("<H", data, 16, response)
                if cts1 != 0:
                    temp_str, _ = self._decode_temperature(cts1)
                    self._add_field(response, "Temp Sensor 1", temp_str, data[16:18])

            # Bytes 18-19: Controller Temperature Sensor 2
            if len(data) >= 20:
                (cts2,) = self._safe_unpack("<H", data, 18, response)
                if cts2 != 0:
                    temp_str, _ = self._decode_temperature(cts2)
                    self._add_field(response, "Temp Sensor 2", temp_str, data[18:20])

            # Bytes 20-23: Power State
            if len(data) >= 24:
                power_state = data[20]
                self._add_field(response, "Power State", power_state, data[20:21])

            # Bytes 24-27: Workload Hint
            if len(data) >= 28:
                (workload,) = self._safe_unpack("<I", data, 24, response)
                if workload != 0:
                    self._add_field(response, "Workload Hint", f"0x{workload:08X}", data[24:28])

            # Bytes 28-31: Vendor Specific
            if len(data) >= 32:
                vendor_data = data[28:32]
                if any(b != 0 for b in vendor_data):
                    self._add_field(
                        response,
                        "Vendor Specific Data",
                        vendor_data.hex(),
                        vendor_data,
                    )

        return response


@DecoderRegistry.register(
    opcode=NVMeMIOpcode.READ_NVME_MI_DATA_STRUCTURE,
    data_type=NVMeDataStructureType.NVM_SUBSYSTEM_INFORMATION,
)
class SubsystemInfoDecoder(ResponseDecoder):
    """
    Decoder for Read NVMe-MI Data Structure - NVM Subsystem Information (Type 0).

    Reference: NVMe-MI 1.2, Section 6.1.1
    """

    def decode(self, data: bytes, response: DecodedResponse) -> DecodedResponse:
        if len(data) < 4:
            response.decode_errors.append(f"Subsystem info too short: {len(data)} bytes")
            return response

        # Byte 0: Number of Ports
        nump = data[0]
        self._add_field(response, "Number of Ports", nump, data[0:1])

        # Byte 1: Major Version
        mjr = data[1]
        self._add_field(response, "NVMe-MI Major Version", mjr, data[1:2])

        # Byte 2: Minor Version
        mnr = data[2]
        self._add_field(response, "NVMe-MI Minor Version", mnr, data[2:3])

        # Combined version string
        self._add_field(response, "NVMe-MI Version", f"{mjr}.{mnr}", data[1:3])

        # Bytes 4-7: Optional Commands Supported bitmap
        if len(data) >= 8:
            (ocs,) = self._safe_unpack("<I", data, 4, response)

            cmd_names = {
                0: "Configuration Set",
                1: "Configuration Get",
                2: "VPD Read",
                3: "VPD Write",
                4: "MI Reset",
                5: "SES Receive",
                6: "SES Send",
                7: "MEB Read",
                8: "MEB Write",
                10: "MI Send",
                11: "MI Receive",
            }

            supported = []
            for bit, name in cmd_names.items():
                if ocs & (1 << bit):
                    supported.append(name)

            self._add_field(
                response,
                "Optional Commands Supported",
                ", ".join(supported) if supported else "None",
                data[4:8],
            )

        return response


@DecoderRegistry.register(
    opcode=NVMeMIOpcode.READ_NVME_MI_DATA_STRUCTURE, data_type=NVMeDataStructureType.CONTROLLER_LIST
)
class ControllerListDecoder(ResponseDecoder):
    """
    Decoder for Read NVMe-MI Data Structure - Controller List (Type 2).
    """

    def decode(self, data: bytes, response: DecodedResponse) -> DecodedResponse:
        if len(data) < 1:
            response.decode_errors.append("Controller list too short")
            return response

        num_entries = data[0]
        self._add_field(response, "Number of Controllers", num_entries, data[0:1])

        controllers = []
        offset = 2  # Skip header bytes
        for i in range(num_entries):
            if offset + 2 > len(data):
                response.decode_errors.append(f"Truncated controller list at entry {i}")
                break
            (ctrlr_id,) = struct.unpack("<H", data[offset : offset + 2])
            controllers.append(ctrlr_id)
            offset += 2

        self._add_field(response, "Controller IDs", controllers, data[2:offset])

        return response


@DecoderRegistry.register(
    opcode=NVMeMIOpcode.READ_NVME_MI_DATA_STRUCTURE,
    data_type=NVMeDataStructureType.PORT_INFORMATION,
)
class PortInfoDecoder(ResponseDecoder):
    """
    Decoder for Read NVMe-MI Data Structure - Port Information (Type 1).
    """

    def decode(self, data: bytes, response: DecodedResponse) -> DecodedResponse:
        if len(data) < 4:
            response.decode_errors.append("Port info too short")
            return response

        # Byte 0: Port Type
        port_type = data[0]
        port_types = {
            0x00: "Not Specified",
            0x01: "PCIe",
            0x02: "SMBus/I2C",
            0x03: "I3C",
        }
        self._add_field(
            response,
            "Port Type",
            port_types.get(port_type, f"Unknown (0x{port_type:02X})"),
            data[0:1],
        )

        # Byte 1: Reserved

        # Bytes 2-3: Max MCTP Transmission Unit
        if len(data) >= 4:
            (mtu,) = struct.unpack("<H", data[2:4])
            self._add_field(response, "Max MCTP Transmission Unit", mtu, data[2:4], unit="bytes")

        # Bytes 4-7: Management Endpoint Buffer Size
        if len(data) >= 8:
            (meb_size,) = struct.unpack("<I", data[4:8])
            self._add_field(response, "MEB Size", meb_size, data[4:8], unit="bytes")

        return response


@DecoderRegistry.register(opcode=NVMeMIOpcode.VPD_READ)
class VPDReadDecoder(ResponseDecoder):
    """
    Decoder for VPD Read Response (Opcode 0x05).
    """

    def decode(self, data: bytes, response: DecodedResponse) -> DecodedResponse:
        if len(data) < 2:
            response.decode_errors.append("VPD response too short")
            return response

        # First 2 bytes are typically data length returned
        (vpd_len,) = struct.unpack("<H", data[0:2])
        self._add_field(response, "VPD Data Length", vpd_len, data[0:2], unit="bytes")

        # VPD data follows
        vpd_data = data[2 : 2 + vpd_len] if len(data) >= 2 + vpd_len else data[2:]

        # Try to decode as ASCII
        try:
            vpd_str = vpd_data.decode("ascii", errors="replace").rstrip("\x00")
            # Check if it looks like valid ASCII
            if vpd_str.isprintable() or len(vpd_str) == 0:
                self._add_field(response, "VPD Content", vpd_str, vpd_data)
            else:
                self._add_field(response, "VPD Content (hex)", vpd_data.hex(), vpd_data)
        except Exception:
            self._add_field(response, "VPD Content (hex)", vpd_data.hex(), vpd_data)

        return response


@DecoderRegistry.register(opcode=NVMeMIOpcode.CONFIGURATION_GET)
class ConfigurationGetDecoder(ResponseDecoder):
    """
    Decoder for Configuration Get Response (Opcode 0x04).
    """

    def decode(self, data: bytes, response: DecodedResponse) -> DecodedResponse:
        if len(data) < 1:
            response.decode_errors.append("Configuration Get response too short")
            return response

        # Configuration data varies by configuration identifier
        # For now, just return raw data
        self._add_field(
            response, "Configuration Data", data.hex(), data, description="Raw configuration data"
        )

        return response


# Generic decoder for unhandled opcodes
@DecoderRegistry.register(opcode=NVMeMIOpcode.READ_NVME_MI_DATA_STRUCTURE)
class GenericDataStructureDecoder(ResponseDecoder):
    """
    Fallback decoder for Read NVMe-MI Data Structure when no specific decoder exists.
    """

    def decode(self, data: bytes, response: DecodedResponse) -> DecodedResponse:
        self._add_field(
            response, "Data Structure", data.hex(), data, description="Raw data structure bytes"
        )
        return response
