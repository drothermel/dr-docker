"""Langfuse primitive integration contract models."""

from pydantic import BaseModel, Field

from .errors import ErrorEnvelope


class PromptFetchRequest(BaseModel):
    """Request contract for fetching a prompt from Langfuse."""

    prompt_name: str
    label: str | None = None
    version: int | None = None
    variables: dict[str, object] = Field(default_factory=dict)


class PromptPayload(BaseModel):
    """Resolved prompt payload returned by Langfuse."""

    prompt_name: str
    system_content: str
    task_content: str
    label: str | None = None
    version: int | None = None


class TraceEventRequest(BaseModel):
    """Request contract for creating or updating a trace event."""

    event_name: str
    session_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class TraceAck(BaseModel):
    """Acknowledgement returned after submitting a trace event."""

    accepted: bool
    trace_id: str | None = None
    error: ErrorEnvelope | None = None
