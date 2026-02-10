"""Docker primitive runtime contract models."""

from pydantic import BaseModel, Field

from .errors import ErrorEnvelope


class DockerMount(BaseModel):
    """Docker bind mount settings."""

    source: str
    target: str
    read_only: bool = False


class DockerRuntimeRequest(BaseModel):
    """Input payload for a primitive Docker runtime execution."""

    image: str
    command: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    mounts: list[DockerMount] = Field(default_factory=list)
    timeout_seconds: int
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
