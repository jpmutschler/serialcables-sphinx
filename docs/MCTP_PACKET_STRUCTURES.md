# NVMe-MI over MCTP Packet Structures for Firmware Shortcuts

This document defines the spec-compliant packet structures for HYDRA firmware shortcuts.

**References:**
- DMTF DSP0236 (MCTP Base Specification)
- DMTF DSP0237 (MCTP SMBus/I2C Transport Binding)
- NVM Express Management Interface Specification 1.2
- NVM Express Management Interface Specification 2.0/2.1 (for Gen6+ devices)

---

## NVMe-MI Version Compatibility

### Version Detection

The NVMe-MI version supported by a device can be determined from the **NVM Subsystem Information** data structure (Read NVMe-MI Data Structure, type 0x00). The response contains:
- Byte 1: NVMe-MI Major Version
- Byte 2: NVMe-MI Minor Version

### NVMe-MI 1.2 vs 2.x Differences

| Feature | NVMe-MI 1.2 (Gen5) | NVMe-MI 2.x (Gen6+) |
|---------|-------------------|---------------------|
| **Admin Command Tunneling** | MI Send (0x0D) / MI Receive (0x0E) | Command Capsule format supported |
| **Max Message Size** | 4224 bytes | Negotiable via MCTP |
| **Subsystem Health Poll Response** | 20 bytes | Extended to 32 bytes |
| **Controller Health Poll Response** | 16 bytes | Extended to 32 bytes |
| **Security Commands** | Not available | 0x12-0x15 added |
| **Boot Partition Commands** | Not available | 0x10-0x11 added |

### New NVMe-MI 2.x Opcodes

| Opcode | Command | Description |
|--------|---------|-------------|
| 0x10 | Get Boot Partition Configuration | Query boot partition settings |
| 0x11 | Set Boot Partition Configuration | Configure boot partition |
| 0x12 | Get Security State | Query device security state |
| 0x13 | Set Security State | Configure security state |
| 0x14 | Security Send | Send security protocol data |
| 0x15 | Security Receive | Receive security protocol data |
| 0x20 | MI Get Features | MI-specific Get Features (2.1+) |
| 0x21 | MI Set Features | MI-specific Set Features (2.1+) |

### Extended Health Status Response (NVMe-MI 2.x)

The 32-byte extended health response adds:

| Offset | Field | Size | Description |
|--------|-------|------|-------------|
| 20-23 | Endurance Group Critical Warning | 4 bytes | Warning flags for endurance groups |
| 24-27 | Reserved | 4 bytes | Reserved for future use |
| 28-31 | Vendor Specific | 4 bytes | Vendor-defined data |

### PCIe Generation Expectations

| PCIe Gen | Typical NVMe-MI Version | Notes |
|----------|------------------------|-------|
| Gen3 | 1.0 - 1.1 | Basic MI support |
| Gen4 | 1.1 - 1.2 | Full MI command set |
| Gen5 | 1.2 | Current production devices |
| Gen6 | 2.0 - 2.1 | Extended features, security |

### Backwards Compatibility

NVMe-MI 2.x devices should support 1.2 commands. The firmware can:
1. Start with 1.2-format packets (works with all devices)
2. Query device version via Read Data Structure (type 0x00)
3. Use extended features only when device reports 2.x support

---

## Packet Structure Overview

### SMBus/I2C Transport Frame (DSP0237)

```
Byte 0:     Destination Slave Address (write)
Byte 1:     Command Code (0x0F for MCTP)
Byte 2:     Byte Count (number of bytes following, excluding PEC)
Byte 3:     Source Slave Address (read address, typically 0x21 for host)
Bytes 4-7:  MCTP Transport Header (4 bytes)
Byte 8:     MCTP Message Type (0x04 for NVMe-MI, or 0x84 with IC bit)
Bytes 9+:   NVMe-MI Message
Last Byte:  PEC (SMBus CRC-8)
```

### MCTP Transport Header (4 bytes, DSP0236)

```
Byte 0: Header Version (0x01)
Byte 1: Destination Endpoint ID
Byte 2: Source Endpoint ID
Byte 3: Message Tag/Flags
        Bit 7:   SOM (Start of Message) - 1 for single packet
        Bit 6:   EOM (End of Message) - 1 for single packet
        Bits 5-4: Packet Sequence (0 for single packet)
        Bit 3:   TO (Tag Owner) - 1 for request originator
        Bits 2-0: Message Tag (0-7, increment per transaction)
```

**Typical value for single-packet request:** `0xC8` (SOM=1, EOM=1, PktSeq=0, TO=1, Tag=0)

### MCTP Message Type Byte

```
Bit 7:   IC (Integrity Check) - if 1, CRC-32C MIC follows payload
Bits 6-0: Message Type (0x04 for NVMe-MI)
```

- `0x04` = NVMe-MI without integrity check
- `0x84` = NVMe-MI with integrity check (requires 4-byte CRC-32C MIC before PEC)

### NVMe-MI Request Header (4 bytes, NVMe-MI Spec Figure 6)

```
Byte 0: NMIMT/ROR
        Bit 7:   ROR (0=Request, 1=Response)
        Bits 6-4: Reserved (0)
        Bits 3-0: NMIMT (NVMe-MI Message Type)
                  0 = Control Primitive
                  1 = MI Command (use this for MI commands)
                  4 = Admin Command (use for tunneled admin)

Byte 1: Opcode (MI or Admin opcode)
Bytes 2-3: Reserved (0x00 0x00)
```

**For MI Commands:** NMIMT/ROR = `0x01` (ROR=0, NMIMT=1)
**For Admin Commands:** NMIMT/ROR = `0x04` (ROR=0, NMIMT=4)

---

## Command Specifications

### 1. `mctp <slot> health` - NVM Subsystem Health Status Poll

**Purpose:** Get overall subsystem health status including temperature, spare capacity, and critical warnings.

**NVMe-MI Opcode:** `0x01` (NVM_SUBSYSTEM_HEALTH_STATUS_POLL)

**Request Data:** None (just the 4-byte MI header)

#### Packet Structure (without IC bit):

| Offset | Value | Description |
|--------|-------|-------------|
| 0 | 0x3A | Destination SMBus address |
| 1 | 0x0F | MCTP command code |
| 2 | 0x09 | Byte count (9 bytes follow) |
| 3 | 0x21 | Source SMBus address |
| 4 | 0x01 | MCTP version |
| 5 | EID | Destination EID (typically 0x00 or 0x01) |
| 6 | 0x00 | Source EID |
| 7 | 0xC8 | SOM=1, EOM=1, TO=1, Tag=0 |
| 8 | 0x04 | Message type (NVMe-MI) |
| 9 | 0x01 | NMIMT/ROR (MI Command Request) |
| 10 | 0x01 | Opcode (Health Status Poll) |
| 11 | 0x00 | Reserved |
| 12 | 0x00 | Reserved |
| 13 | PEC | SMBus CRC-8 |

**Total: 14 bytes**

#### Expected Response Data (20 bytes payload after MI header):

| Offset | Field | Size |
|--------|-------|------|
| 0-3 | MI Response Header | 4 bytes |
| 4 | NVM Subsystem Status | 1 byte |
| 5 | SMART Warnings | 1 byte |
| 6 | Composite Temperature (LSB) | 1 byte |
| 7 | Composite Temperature (MSB) | 1 byte |
| 8 | Percentage Drive Life Used | 1 byte |
| 9 | Available Spare | 1 byte |
| 10-19 | Reserved | 10 bytes |

---

### 2. `mctp <slot> id` - Identify Controller (Admin Tunneled)

**Purpose:** Get NVMe Identify Controller data (serial number, model, firmware revision, etc.)

**NVMe-MI Opcode:** `0x0D` (MI_SEND) followed by `0x0E` (MI_RECEIVE)

**Admin Opcode:** `0x06` (Identify)

This requires the MI Send/MI Receive mechanism to tunnel Admin commands.

#### MI Send Request Structure:

| Offset | Value | Description |
|--------|-------|-------------|
| 0 | 0x3A | Destination SMBus address |
| 1 | 0x0F | MCTP command code |
| 2 | varies | Byte count |
| 3 | 0x21 | Source SMBus address |
| 4 | 0x01 | MCTP version |
| 5 | EID | Destination EID |
| 6 | 0x00 | Source EID |
| 7 | 0xC8 | SOM=1, EOM=1, TO=1, Tag=0 |
| 8 | 0x04 | Message type (NVMe-MI) |
| 9 | 0x04 | NMIMT/ROR (Admin Command Request) |
| 10 | 0x06 | Admin Opcode (Identify) |
| 11-14 | NSID | Namespace ID (0 for controller) |
| 15-18 | 0x00 | CDW2 |
| 19-22 | 0x00 | CDW3 |
| 23-26 | 0x00 | CDW4 |
| 27-30 | 0x00 | CDW5 |
| 31-34 | 0x00 | CDW6 |
| 35-38 | 0x00 | CDW7 |
| 39-42 | 0x00 | CDW8 |
| 43-46 | 0x00 | CDW9 |
| 47-50 | CNS=0x01 | CDW10 (CNS=1 for Identify Controller) |
| 51-54 | 0x00 | CDW11 |
| 55-58 | 0x00 | CDW12 |
| 59-62 | 0x00 | CDW13 |
| 63-66 | 0x00 | CDW14 |
| 67-70 | 0x00 | CDW15 |
| Last | PEC | SMBus CRC-8 |

**Note:** The response is 4096 bytes and will require fragmented MCTP packets.

#### Key Response Fields (Identify Controller structure):

| Offset | Field | Size |
|--------|-------|------|
| 4-23 | Serial Number | 20 bytes (ASCII) |
| 24-63 | Model Number | 40 bytes (ASCII) |
| 64-71 | Firmware Revision | 8 bytes (ASCII) |

---

### 3. `mctp <slot> smart` - SMART / Health Information Log

**Purpose:** Get detailed SMART health information log page.

**Admin Opcode:** `0x02` (Get Log Page)
**Log Page ID:** `0x02` (SMART / Health Information)

#### MI Send Request Structure:

| Offset | Value | Description |
|--------|-------|-------------|
| 0-8 | ... | SMBus + MCTP header (same as above) |
| 9 | 0x04 | NMIMT/ROR (Admin Command Request) |
| 10 | 0x02 | Admin Opcode (Get Log Page) |
| 11-14 | 0xFFFFFFFF | NSID (all namespaces) |
| 15-46 | 0x00 | CDW2-CDW9 |
| 47-50 | CDW10 | LID=0x02, NUMDL (lower 16 bits of dwords to read - 1) |
| 51-54 | CDW11 | NUMDU (upper 16 bits), LSP, RAE |
| 55-58 | CDW12 | Log Page Offset Lower |
| 59-62 | CDW13 | Log Page Offset Upper |
| 63-70 | 0x00 | CDW14-CDW15 |
| Last | PEC | SMBus CRC-8 |

**CDW10 Format:**
- Bits 7-0: LID (Log Page Identifier) = 0x02
- Bits 15-8: LSP (Log Specific Parameter) = 0x00
- Bits 27-16: NUMDL (Number of Dwords Lower) = 0x7F (128 dwords = 512 bytes - 1)

**CDW10 value for 512-byte SMART log:** `0x007F0002`

#### SMART Log Page Response (512 bytes):

| Offset | Field | Size |
|--------|-------|------|
| 0 | Critical Warning | 1 byte |
| 1-2 | Composite Temperature | 2 bytes (Kelvin) |
| 3 | Available Spare | 1 byte (%) |
| 4 | Available Spare Threshold | 1 byte (%) |
| 5 | Percentage Used | 1 byte (%) |
| 6-31 | Reserved | 26 bytes |
| 32-47 | Data Units Read | 16 bytes |
| 48-63 | Data Units Written | 16 bytes |
| 64-79 | Host Read Commands | 16 bytes |
| 80-95 | Host Write Commands | 16 bytes |
| 96-111 | Controller Busy Time | 16 bytes |
| 112-127 | Power Cycles | 16 bytes |
| 128-143 | Power On Hours | 16 bytes |
| 144-159 | Unsafe Shutdowns | 16 bytes |
| 160-175 | Media Errors | 16 bytes |
| 176-191 | Error Log Entries | 16 bytes |
| 192-195 | Warning Temp Time | 4 bytes |
| 196-199 | Critical Temp Time | 4 bytes |
| 200-215 | Temperature Sensors | 8x 2 bytes |

---

### 4. `mctp <slot> fw` - Firmware Slot Information Log

**Purpose:** Get firmware revision for all slots and active slot info.

**Admin Opcode:** `0x02` (Get Log Page)
**Log Page ID:** `0x03` (Firmware Slot Information)

#### MI Send Request:

Same structure as SMART, but:
- **CDW10:** LID = `0x03`, NUMDL for 512 bytes
- **CDW10 value:** `0x007F0003`

#### Firmware Slot Log Response (512 bytes):

| Offset | Field | Size |
|--------|-------|------|
| 0 | Active Firmware Info (AFI) | 1 byte |
| 1-7 | Reserved | 7 bytes |
| 8-15 | Firmware Revision Slot 1 | 8 bytes (ASCII) |
| 16-23 | Firmware Revision Slot 2 | 8 bytes (ASCII) |
| 24-31 | Firmware Revision Slot 3 | 8 bytes (ASCII) |
| 32-39 | Firmware Revision Slot 4 | 8 bytes (ASCII) |
| 40-47 | Firmware Revision Slot 5 | 8 bytes (ASCII) |
| 48-55 | Firmware Revision Slot 6 | 8 bytes (ASCII) |
| 56-63 | Firmware Revision Slot 7 | 8 bytes (ASCII) |

**AFI Byte:**
- Bits 2-0: Active Firmware Slot
- Bits 6-4: Next Reset Firmware Slot

---

### 5. `mctp <slot> errors` - Error Information Log

**Purpose:** Get error log entries for diagnostics.

**Admin Opcode:** `0x02` (Get Log Page)
**Log Page ID:** `0x01` (Error Information)

#### MI Send Request:

Same structure as SMART, but:
- **CDW10:** LID = `0x01`, NUMDL for desired size
- Typical request: 1-64 error entries, each 64 bytes
- **CDW10 value for 1 entry (64 bytes = 16 dwords):** `0x000F0001`

#### Error Log Entry (64 bytes each):

| Offset | Field | Size |
|--------|-------|------|
| 0-7 | Error Count | 8 bytes |
| 8-9 | Submission Queue ID | 2 bytes |
| 10-11 | Command ID | 2 bytes |
| 12-13 | Status Field | 2 bytes |
| 14-15 | Parameter Error Location | 2 bytes |
| 16-23 | LBA | 8 bytes |
| 24-27 | Namespace | 4 bytes |
| 28 | Vendor Specific Info Available | 1 byte |
| 29 | Transport Type | 1 byte |
| 30-31 | Reserved | 2 bytes |
| 32-39 | Command Specific Info | 8 bytes |
| 40-41 | Transport Type Specific | 2 bytes |
| 42-63 | Reserved | 22 bytes |

---

### 6. `mctp <slot> logs` - Supported Log Pages

**Purpose:** Discover which log pages the device supports.

**Admin Opcode:** `0x02` (Get Log Page)
**Log Page ID:** `0x00` (Supported Log Pages)

#### MI Send Request:

Same structure as SMART, but:
- **CDW10:** LID = `0x00`
- **CDW10 value:** `0x007F0000` (for 512 bytes)

#### Response:

Returns a list of supported log page identifiers with attributes.

| Offset | Field | Size |
|--------|-------|------|
| 0-3 | Number of Log Page Descriptors | 2 bytes (header) |
| 4+ | Log Page Descriptors | 4 bytes each |

Each descriptor:
- Bytes 0-1: Log Page Identifier
- Byte 2: Log Page Attributes
- Byte 3: Reserved

---

### 7. `mctp <slot> thermal` - Temperature Information

**Purpose:** Get temperature sensor readings and thresholds.

This can be obtained from:
1. **Health Status Poll** (quick - composite temp only)
2. **SMART Log Page** (detailed - up to 8 temperature sensors)
3. **Get Features** for temperature thresholds

#### Option A: Use Health Status Poll (simplest)
See `mctp <slot> health` above - composite temperature is in bytes 6-7 of response.

#### Option B: Use SMART Log Page
See `mctp <slot> smart` above - temperature sensors at offsets 200-215.

#### Option C: Get Features - Temperature Threshold

**Admin Opcode:** `0x0A` (Get Features)
**Feature ID:** `0x04` (Temperature Threshold)

| Offset | Value | Description |
|--------|-------|-------------|
| 9 | 0x04 | NMIMT/ROR (Admin Command Request) |
| 10 | 0x0A | Admin Opcode (Get Features) |
| 47-50 | CDW10 | FID=0x04, SEL=0 (current) |
| 51-54 | CDW11 | THSEL (threshold select), TMPSEL (sensor) |

**CDW10:** `0x00000004` (FID = Temperature Threshold)
**CDW11:** THSEL in bits 21-20, TMPSEL in bits 19-16

---

## PEC Calculation (SMBus CRC-8)

The PEC is calculated over all bytes from the destination address through the payload (excluding the PEC itself).

**Polynomial:** x^8 + x^2 + x^1 + 1 (0x07)

```python
def calculate_pec(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = (crc << 1) ^ 0x07
            else:
                crc <<= 1
            crc &= 0xFF
    return crc
```

---

## CRC-32C Calculation (for IC bit)

If the IC (Integrity Check) bit is set in the message type byte (0x84 instead of 0x04), a 4-byte CRC-32C MIC must be appended after the NVMe-MI payload, before the PEC.

**Polynomial:** 0x1EDC6F41 (Castagnoli), reflected form: 0x82F63B78

```python
def calculate_crc32c(data: bytes) -> int:
    poly = 0x82F63B78
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ poly
            else:
                crc >>= 1
    return crc ^ 0xFFFFFFFF
```

The MIC is calculated over the message type byte + NVMe-MI payload.

---

## Quick Reference: Opcodes

| Command | Type | Opcode | Log Page ID |
|---------|------|--------|-------------|
| health | MI | 0x01 | - |
| id | Admin | 0x06 | - |
| smart | Admin | 0x02 | 0x02 |
| fw | Admin | 0x02 | 0x03 |
| errors | Admin | 0x02 | 0x01 |
| logs | Admin | 0x02 | 0x00 |
| thermal | MI/Admin | 0x01 or 0x02/0x0A | - or 0x02 |

---

## Example: Complete Health Status Poll Packet

For slot 2 (EID=0 typically for management endpoint):

```
Bytes: 3A 0F 09 21 01 00 00 C8 04 01 01 00 00 [PEC]

Breakdown:
  3A       Dest SMBus addr (0x3A = NVMe-MI default)
  0F       MCTP command code
  09       Byte count (9 bytes follow, excluding PEC)
  21       Source SMBus addr
  01       MCTP version
  00       Dest EID
  00       Source EID
  C8       SOM=1, EOM=1, TO=1, Tag=0
  04       NVMe-MI message type (no IC)
  01       NMIMT/ROR = MI Command Request
  01       Opcode = Health Status Poll
  00       Reserved
  00       Reserved
  [PEC]    Calculate CRC-8 over bytes 0-12
```

Calculate PEC: `calculate_pec(bytes.fromhex('3A0F092101000C804010100 00'))`

The response will come back with similar framing, with NMIMT/ROR = 0x02 (MI Response) and status + health data.
