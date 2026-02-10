"""Langfuse primitive integration contract models."""

from pydantic import BaseModel, Field, model_validator

from .errors import ErrorEnvelope


class PromptFetchRequest(BaseModel):
    """Request contract for fetching a prompt from Langfuse."""

    prompt_name: str = Field(min_length=1)
    label: str | None = None
    version: int | None = None
    variables: dict[str, object] = Field(default_factory=dict)


class PromptPayload(BaseModel):
    """Resolved prompt payload returned by Langfuse."""

    prompt_name: str
    system_content: str | None = None
    task_content: str = Field(min_length=1)
    label: str | None = None
    version: int | None = None


class TraceEventRequest(BaseModel):
    """Request contract for creating or updating a trace event."""

    event_name: str = Field(min_length=1)
    session_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


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
