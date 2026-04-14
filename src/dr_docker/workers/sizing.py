"""Reusable byte-size parsing helpers for worker configuration."""

from __future__ import annotations


def parse_byte_size(value: str) -> int:
    """Parse a byte-size string into an integer number of bytes.

    Supports raw integer byte strings and ``k``/``m``/``g`` suffixes
    case-insensitively. Decimal magnitudes are allowed for suffixed values.
    """

    normalized = value.strip().lower()
    if not normalized:
        raise ValueError("byte-size value must not be empty")

    multipliers = {
        "k": 1024,
        "m": 1024**2,
        "g": 1024**3,
    }
    suffix = normalized[-1:]
    if suffix in multipliers:
        return int(float(normalized[:-1]) * multipliers[suffix])
    return int(normalized)
