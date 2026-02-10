"""Internal helpers for strict JSON boundary validation."""

from __future__ import annotations

import math

from pydantic import JsonValue


def ensure_finite_json_value(value: JsonValue, *, path: str) -> None:
    """Reject non-finite numbers to preserve deterministic JSON contracts."""

    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must not contain NaN or infinity")
        return

    if isinstance(value, list):
        for index, item in enumerate(value):
            ensure_finite_json_value(item, path=f"{path}[{index}]")
        return

    if isinstance(value, dict):
        for key, item in value.items():
            ensure_finite_json_value(item, path=f"{path}.{key}")
