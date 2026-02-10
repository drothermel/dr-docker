"""Langfuse primitive integration contract models."""

from pydantic import BaseModel, Field, JsonValue, field_validator, model_validator

from ._json_validation import ensure_finite_json_value
from .errors import ErrorEnvelope


class PromptFetchRequest(BaseModel):
    """Request contract for fetching a prompt from Langfuse."""

    prompt_name: str = Field(min_length=1)
    label: str | None = None
    version: int | None = None
    variables: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("variables")
    @classmethod
    def _ensure_json_safe_variables(
        cls, variables: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        for key, value in variables.items():
            ensure_finite_json_value(value, path=f"variables.{key}")
        return variables


class PromptPayload(BaseModel):
    """Resolved prompt payload returned by Langfuse."""

    prompt_name: str = Field(min_length=1)
    system_content: str = ""
    task_content: str = Field(min_length=1)
    label: str | None = None
    version: int | None = None


class TraceEventRequest(BaseModel):
    """Request contract for creating or updating a trace event."""

    event_name: str = Field(min_length=1)
    session_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def _ensure_json_safe_metadata(
        cls, metadata: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        for key, value in metadata.items():
            ensure_finite_json_value(value, path=f"metadata.{key}")
        return metadata


class TraceAck(BaseModel):
    """Acknowledgement returned after submitting a trace event."""

    accepted: bool
    trace_id: str | None = None
    error: ErrorEnvelope | None = None

    @model_validator(mode="after")
    def _reject_accepted_with_error(self) -> "TraceAck":
        if self.accepted and self.error is not None:
            raise ValueError("error must be null when accepted is true")
        if not self.accepted and self.error is None:
            raise ValueError("error must be present when accepted is false")
        return self
