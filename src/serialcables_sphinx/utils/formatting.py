"""
Formatting utilities for hex data and output.
"""

from typing import Union


def format_hex(data: Union[bytes, int], prefix: bool = True) -> str:
    """
    Format bytes or int as hex string.

    Args:
        data: Bytes or integer to format
        prefix: Include '0x' prefix

    Returns:
        Formatted hex string
    """
    if isinstance(data, int):
        hex_str = f"{data:02X}"
    else:
        hex_str = data.hex().upper()

    return f"0x{hex_str}" if prefix else hex_str


def format_bytes(
    data: bytes,
    sep: str = " ",
    group: int = 0,
    uppercase: bool = True,
) -> str:
    """
    Format bytes as spaced hex string.

    Args:
        data: Bytes to format
        sep: Separator between bytes
        group: Group size (0 for no grouping)
        uppercase: Use uppercase hex

    Returns:
        Formatted string like "3A 0F 11 21"
    """
    hex_chars = data.hex()
    if uppercase:
        hex_chars = hex_chars.upper()

    # Split into byte pairs
    pairs = [hex_chars[i : i + 2] for i in range(0, len(hex_chars), 2)]

    if group > 0:
        # Group bytes
        groups = [pairs[i : i + group] for i in range(0, len(pairs), group)]
        return "  ".join(sep.join(g) for g in groups)

    return sep.join(pairs)


def parse_hex_string(hex_str: str) -> bytes:
    """
    Parse hex string to bytes.

    Accepts various formats:
    - "3A 0F 11" (space-separated)
    - "3A,0F,11" (comma-separated)
    - "3A0F11" (continuous)
    - "0x3A 0x0F" (with prefixes)

    Args:
        hex_str: Hex string to parse

    Returns:
        Parsed bytes
    """
    # Normalize
    hex_str = hex_str.replace(",", " ")
    hex_str = hex_str.replace("0x", " ")
    hex_str = hex_str.replace("0X", " ")

    parts = hex_str.split()

    if len(parts) == 1 and len(parts[0]) > 2:
        # Continuous hex string
        hex_str = parts[0]
        return bytes.fromhex(hex_str)

    # Space-separated
    return bytes(int(p, 16) for p in parts)


def hexdump(
    data: bytes,
    offset: int = 0,
    width: int = 16,
    show_ascii: bool = True,
) -> str:
    """
    Format bytes as hexdump.

    Args:
        data: Bytes to dump
        offset: Starting offset for addresses
        width: Bytes per line
        show_ascii: Include ASCII representation

    Returns:
        Multi-line hexdump string
    """
    lines = []

    for i in range(0, len(data), width):
        chunk = data[i : i + width]
        addr = offset + i

        # Hex bytes
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        hex_part = hex_part.ljust(width * 3 - 1)

        # ASCII representation
        if show_ascii:
            ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            lines.append(f"{addr:08X}  {hex_part}  |{ascii_part}|")
        else:
            lines.append(f"{addr:08X}  {hex_part}")

    return "\n".join(lines)
