"""Shared typed error envelope contracts."""

from enum import Enum

from pydantic import BaseModel, Field, JsonValue, field_validator

from ._json_validation import ensure_finite_json_value


class ErrorCode(str, Enum):
    """Canonical error codes for primitive runtime integrations."""

    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    AUTH = "auth"
    MALFORMED_REQUEST = "malformed_request"
    INTERNAL_ERROR = "internal_error"


class ErrorEnvelope(BaseModel):
    """Standard error payload shared across primitive contracts."""

    code: ErrorCode
    message: str = Field(min_length=1)
    retriable: bool = False
    details: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("details")
    @classmethod
    def _ensure_json_safe_details(
        cls, details: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        for key, value in details.items():
            ensure_finite_json_value(value, path=f"details.{key}")
        return details
