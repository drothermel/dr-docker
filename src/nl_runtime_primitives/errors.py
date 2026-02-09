"""Shared typed error envelope contracts."""

from enum import Enum

from pydantic import BaseModel, Field


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
    message: str
    retriable: bool = False
    details: dict[str, object] = Field(default_factory=dict)
