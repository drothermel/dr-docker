"""Docker primitive runtime contract models."""

from pydantic import BaseModel, Field, model_validator

from .errors import ErrorEnvelope


class DockerMount(BaseModel):
    """Docker bind mount settings."""

    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    read_only: bool = False


class DockerRuntimeRequest(BaseModel):
    """Input payload for a primitive Docker runtime execution."""

    image: str = Field(min_length=1)
    command: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    mounts: list[DockerMount] = Field(default_factory=list)
    timeout_seconds: int = Field(gt=0)
    working_dir: str | None = None


class DockerRuntimeResult(BaseModel):
    """Output payload for a primitive Docker runtime execution."""

    ok: bool
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float | None = None
    container_id: str | None = None
    error: ErrorEnvelope | None = None

    @model_validator(mode="after")
    def _reject_success_with_error(self) -> "DockerRuntimeResult":
        if self.ok and self.error is not None:
            raise ValueError("error must be null when ok is true")
        if not self.ok and self.error is None:
            raise ValueError("error must be present when ok is false")
        return self
