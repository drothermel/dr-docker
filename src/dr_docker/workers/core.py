"""Higher-level helpers for mounted worker execution in Docker."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import logging
import os
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..docker_contract import (
    DockerMount,
    DockerRuntimeRequest,
    ResourceLimits,
    SecurityProfile,
    TmpfsMount,
)

DEFAULT_WORKER_MOUNT_TARGET = "/worker"
DEFAULT_WORKER_TMPFS_TARGET = "/tmp"
LOGGER = logging.getLogger(__name__)


def _normalize_absolute_container_path(
    value: str | None, *, field_name: str
) -> str | None:
    if value is None:
        return None
    path = PurePosixPath(value)
    if not path.is_absolute():
        raise ValueError(f"{field_name} must be an absolute POSIX path")
    return str(path)


def _normalize_relative_container_path(value: str | None) -> str | None:
    if value is None:
        return None
    path = PurePosixPath(value)
    if path.is_absolute():
        raise ValueError(
            "relative_path must be relative to the mounted worker directory"
        )
    if ".." in path.parts:
        raise ValueError("relative_path must not escape the mounted worker directory")
    return str(path)


def _resolve_existing_source(source: str | Path, *, expected: str) -> Path:
    source_path = Path(source).expanduser()
    if expected == "file":
        if not source_path.is_file():
            raise ValueError(f"worker source file does not exist: {source_path}")
    elif expected == "directory":
        if not source_path.is_dir():
            raise ValueError(f"worker source directory does not exist: {source_path}")
    else:
        raise ValueError(f"unknown expected source type: {expected}")
    return source_path.resolve()


def _parse_int_env(
    environ: Mapping[str, str],
    env_name: str,
    current_value: int | None,
) -> int | None:
    raw_value = environ.get(env_name)
    if raw_value is None:
        return current_value
    try:
        return int(raw_value)
    except ValueError:
        LOGGER.warning(
            "Invalid integer for %s=%r, preserving current value %r",
            env_name,
            raw_value,
            current_value,
        )
        return current_value


def _parse_float_env(
    environ: Mapping[str, str],
    env_name: str,
    current_value: float,
) -> float:
    raw_value = environ.get(env_name)
    if raw_value is None:
        return current_value
    try:
        return float(raw_value)
    except ValueError:
        LOGGER.warning(
            "Invalid float for %s=%r, preserving current value %r",
            env_name,
            raw_value,
            current_value,
        )
        return current_value


def _parse_bool_env(
    environ: Mapping[str, str],
    env_name: str,
    current_value: bool,
) -> bool:
    raw_value = environ.get(env_name)
    if raw_value is None:
        return current_value
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    LOGGER.warning(
        "Invalid boolean for %s=%r, preserving current value %r",
        env_name,
        raw_value,
        current_value,
    )
    return current_value


class WorkerRuntimePolicy(BaseModel):
    """Reusable Docker policy defaults for a small isolated worker runtime."""

    model_config = ConfigDict(frozen=True)

    memory: str = Field(default="512m", min_length=1)
    cpus: float = Field(default=1.0, gt=0)
    pids_limit: int = Field(default=256, gt=0)
    cpu_seconds: int | None = Field(default=None, gt=0)
    tmpfs_size: str = Field(default="64m", min_length=1)
    tmpfs_target: str = DEFAULT_WORKER_TMPFS_TARGET
    tmpfs_exec: bool = False
    fsize_bytes: int | None = Field(default=10_485_760, gt=0)
    nofile: int | None = Field(default=1024, gt=0)
    nproc: int | None = Field(default=256, gt=0)

    @field_validator("tmpfs_target")
    @classmethod
    def _validate_tmpfs_target(cls, value: str) -> str:
        normalized = _normalize_absolute_container_path(
            value,
            field_name="tmpfs_target",
        )
        assert normalized is not None
        return normalized

    @classmethod
    def small_isolated(cls) -> "WorkerRuntimePolicy":
        """Return the default preset for a small isolated worker container."""
        return cls()

    def with_env_overrides(
        self,
        *,
        prefix: str = "DR_DOCKER_",
        environ: Mapping[str, str] | None = None,
    ) -> "WorkerRuntimePolicy":
        """Return a copy with env-based overrides applied."""

        env = environ or os.environ
        pids_env_name = f"{prefix}PIDS_LIMIT"
        nproc_env_name = f"{prefix}NPROC"
        pids_limit = _parse_int_env(env, pids_env_name, self.pids_limit)
        nproc = _parse_int_env(env, nproc_env_name, self.nproc)
        if pids_env_name in env and nproc_env_name not in env:
            nproc = pids_limit

        return self.model_copy(
            update={
                "memory": env.get(f"{prefix}MEMORY", self.memory),
                "cpus": _parse_float_env(env, f"{prefix}CPUS", self.cpus),
                "pids_limit": pids_limit,
                "cpu_seconds": _parse_int_env(
                    env,
                    f"{prefix}CPU_SECONDS",
                    self.cpu_seconds,
                ),
                "tmpfs_size": env.get(f"{prefix}TMPFS_SIZE", self.tmpfs_size),
                "tmpfs_target": env.get(f"{prefix}TMPFS_TARGET", self.tmpfs_target),
                "tmpfs_exec": _parse_bool_env(
                    env,
                    f"{prefix}TMPFS_EXEC",
                    self.tmpfs_exec,
                ),
                "fsize_bytes": _parse_int_env(
                    env,
                    f"{prefix}FSIZE_BYTES",
                    self.fsize_bytes,
                ),
                "nofile": _parse_int_env(env, f"{prefix}NOFILE", self.nofile),
                "nproc": nproc,
            }
        )

    def to_resource_limits(self) -> ResourceLimits:
        return ResourceLimits(
            memory=self.memory,
            cpus=self.cpus,
            pids_limit=self.pids_limit,
            cpu_seconds=self.cpu_seconds,
            fsize_bytes=self.fsize_bytes,
            nofile=self.nofile,
            nproc=self.nproc,
        )

    def to_tmpfs_mounts(self) -> list[TmpfsMount]:
        return [
            TmpfsMount(
                target=self.tmpfs_target,
                size=self.tmpfs_size,
                exec_=self.tmpfs_exec,
            )
        ]


class MountedWorker(BaseModel):
    """Mounted worker source plus execution settings for a container run."""

    model_config = ConfigDict(frozen=True)

    source: str = Field(min_length=1)
    mount_target: str = Field(min_length=1)
    container_path: str = Field(min_length=1)
    read_only: bool = True
    entrypoint: str | None = None
    command: list[str] = Field(default_factory=list)
    working_dir: str | None = None

    @field_validator("mount_target")
    @classmethod
    def _validate_mount_target(cls, value: str) -> str:
        normalized = _normalize_absolute_container_path(
            value,
            field_name="mount_target",
        )
        assert normalized is not None
        return normalized

    @field_validator("container_path")
    @classmethod
    def _validate_container_path(cls, value: str) -> str:
        normalized = _normalize_absolute_container_path(
            value,
            field_name="container_path",
        )
        assert normalized is not None
        return normalized

    @field_validator("working_dir")
    @classmethod
    def _validate_working_dir(cls, value: str | None) -> str | None:
        return _normalize_absolute_container_path(value, field_name="working_dir")

    @model_validator(mode="after")
    def _validate_container_path_below_mount(self) -> "MountedWorker":
        mount_target = PurePosixPath(self.mount_target)
        container_path = PurePosixPath(self.container_path)
        if not container_path.is_relative_to(mount_target):
            raise ValueError("container_path must be inside mount_target")
        return self

    def to_mount(self) -> DockerMount:
        return DockerMount(
            source=self.source,
            target=self.mount_target,
            read_only=self.read_only,
        )

    def with_path_command(
        self,
        *,
        entrypoint: str | None = None,
        args_before_path: Sequence[str] = (),
        args_after_path: Sequence[str] = (),
        working_dir: str | None = None,
    ) -> "MountedWorker":
        """Return a copy that invokes the resolved container path."""

        return self.model_copy(
            update={
                "entrypoint": entrypoint if entrypoint is not None else self.entrypoint,
                "command": [
                    *list(args_before_path),
                    self.container_path,
                    *list(args_after_path),
                ],
                "working_dir": working_dir
                if working_dir is not None
                else self.working_dir,
            }
        )


def mount_worker_file(
    source: str | Path,
    *,
    mount_target: str = DEFAULT_WORKER_MOUNT_TARGET,
    read_only: bool = True,
) -> MountedWorker:
    """Mount a single worker file by mounting its parent directory read-only."""

    source_path = _resolve_existing_source(source, expected="file")
    mount_root = PurePosixPath(mount_target)
    container_path = mount_root / source_path.name
    return MountedWorker(
        source=str(source_path.parent),
        mount_target=str(mount_root),
        container_path=str(container_path),
        read_only=read_only,
    )


def mount_worker_directory(
    source: str | Path,
    *,
    mount_target: str = DEFAULT_WORKER_MOUNT_TARGET,
    relative_path: str | None = None,
    read_only: bool = True,
) -> MountedWorker:
    """Mount a worker directory and optionally point at a nested path inside it."""

    source_path = _resolve_existing_source(source, expected="directory")
    normalized_relative_path = _normalize_relative_container_path(relative_path)
    mount_root = PurePosixPath(mount_target)
    container_path = mount_root
    if normalized_relative_path is not None:
        container_path = mount_root / PurePosixPath(normalized_relative_path)
    return MountedWorker(
        source=str(source_path),
        mount_target=str(mount_root),
        container_path=str(container_path),
        read_only=read_only,
    )


def build_mounted_worker_request(
    *,
    image: str,
    worker: MountedWorker,
    timeout_seconds: int,
    policy: WorkerRuntimePolicy | None = None,
    stdin_payload: bytes | str | None = None,
    env: Mapping[str, str] | None = None,
    extra_mounts: Sequence[DockerMount] | None = None,
    extra_tmpfs: Sequence[TmpfsMount] | None = None,
    security: SecurityProfile | None = None,
) -> DockerRuntimeRequest:
    """Build a DockerRuntimeRequest for a mounted worker with policy defaults."""

    runtime_policy = policy or WorkerRuntimePolicy.small_isolated()
    encoded_stdin_payload: bytes | None
    if isinstance(stdin_payload, str):
        encoded_stdin_payload = stdin_payload.encode("utf-8")
    else:
        encoded_stdin_payload = stdin_payload

    mounts = [worker.to_mount(), *(extra_mounts or ())]
    tmpfs = [*runtime_policy.to_tmpfs_mounts(), *(extra_tmpfs or ())]

    return DockerRuntimeRequest(
        image=image,
        command=list(worker.command),
        entrypoint=worker.entrypoint,
        env=dict(env or {}),
        mounts=mounts,
        tmpfs=tmpfs,
        timeout_seconds=timeout_seconds,
        working_dir=worker.working_dir,
        stdin_payload=encoded_stdin_payload,
        security=security or SecurityProfile(),
        resources=runtime_policy.to_resource_limits(),
    )
