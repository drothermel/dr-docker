"""Docker primitive runtime contract models."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from .errors import ErrorEnvelope


class DockerMount(BaseModel):
    """Docker bind mount settings."""

    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    read_only: bool = False


class SecurityProfile(BaseModel):
    """Container security hardening."""

    read_only: bool = True
    cap_drop: str = "ALL"
    no_new_privileges: bool = True
    network_disabled: bool = True


class ResourceLimits(BaseModel):
    """Container resource constraints."""

    memory: str = "256m"
    cpus: float = 0.5
    pids_limit: int = 64
    cpu_seconds: int | None = None
    fsize_bytes: int | None = None
    nofile: int | None = None
    nproc: int | None = None


class TmpfsMount(BaseModel):
    """Tmpfs mount specification."""

    target: str = "/tmp"
    size: str = "16m"
    exec: bool = False


class DockerRuntimeRequest(BaseModel):
    """Input payload for a primitive Docker runtime execution."""

    image: str = Field(min_length=1)
    command: list[str] = Field(default_factory=list)
    entrypoint: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    mounts: list[DockerMount] = Field(default_factory=list)
    tmpfs: list[TmpfsMount] = Field(default_factory=list)
    timeout_seconds: int = Field(gt=0)
    working_dir: str | None = None
    stdin_payload: bytes | None = None
    security: SecurityProfile = Field(default_factory=SecurityProfile)
    resources: ResourceLimits = Field(default_factory=ResourceLimits)


class DockerRuntimeResult(BaseModel):
    """Output payload for a primitive Docker runtime execution."""

    ok: bool
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float | None = Field(default=None, ge=0)
    container_id: str | None = None
    error: ErrorEnvelope | None = None

    @model_validator(mode="after")
    def _reject_success_with_error(self) -> DockerRuntimeResult:
        if self.ok and self.error is not None:
            raise ValueError("error must be null when ok is true")
        if not self.ok and self.error is None:
            raise ValueError("error must be present when ok is false")
        return self
