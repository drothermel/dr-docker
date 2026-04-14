"""Optional helpers for JSON-over-stdin workers running inside containers."""

from __future__ import annotations

from collections.abc import Mapping
import json
import logging
import math
import os
import resource
import sys
from typing import Any, TextIO

from pydantic import BaseModel, ConfigDict, Field

from .core import WorkerRuntimePolicy
from .sizing import parse_byte_size

LOGGER = logging.getLogger(__name__)
DEFAULT_WORKER_ENV_PREFIX = "DR_DOCKER_WORKER_"
DEFAULT_WORKER_IN_CONTAINER_ENV_VAR = f"{DEFAULT_WORKER_ENV_PREFIX}IN_CONTAINER"


class OversizedPayloadError(ValueError):
    """Raised when stdin exceeds the configured maximum byte size."""

    def __init__(self, max_bytes: int, actual_bytes: int) -> None:
        super().__init__(
            f"stdin payload exceeds limit ({actual_bytes} > {max_bytes} bytes)"
        )
        self.max_bytes = max_bytes
        self.actual_bytes = actual_bytes


class DockerOnlyExecutionError(RuntimeError):
    """Raised when a worker is executed outside the expected container path."""


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


def _parse_byte_size_env(
    environ: Mapping[str, str],
    env_name: str,
    current_value: int | None,
) -> int | None:
    raw_value = environ.get(env_name)
    if raw_value is None:
        return current_value
    try:
        return parse_byte_size(raw_value)
    except ValueError:
        LOGGER.warning(
            "Invalid byte size for %s=%r, preserving current value %r",
            env_name,
            raw_value,
            current_value,
        )
        return current_value


class BoundedTextCapture:
    """A text sink that caps the stored UTF-8 output by byte size."""

    def __init__(self, limit_bytes: int) -> None:
        if limit_bytes <= 0:
            raise ValueError("limit_bytes must be positive")
        self._limit_bytes = limit_bytes
        self._used_bytes = 0
        self._parts: list[str] = []
        self.truncated = False

    def write(self, value: str) -> int:
        encoded = value.encode("utf-8")
        remaining = self._limit_bytes - self._used_bytes
        if remaining <= 0:
            self.truncated = True
            return len(value)

        if len(encoded) <= remaining:
            self._parts.append(value)
            self._used_bytes += len(encoded)
            return len(value)

        self.truncated = True
        kept = encoded[:remaining].decode("utf-8", errors="ignore")
        if kept:
            self._parts.append(kept)
            self._used_bytes += len(kept.encode("utf-8"))
        return len(value)

    def flush(self) -> None:
        return None

    def getvalue(self) -> str:
        return "".join(self._parts)


class JsonWorkerExecutionConfig(BaseModel):
    """Typed execution config for JSON-over-stdin workers."""

    model_config = ConfigDict(frozen=True)

    stdin_limit_bytes: int = Field(default=1_048_576, gt=0)
    stdout_limit_bytes: int = Field(default=1_048_576, gt=0)
    cpu_seconds: int = Field(default=2, gt=0)
    memory_bytes: int = Field(default=268_435_456, gt=0)
    file_bytes: int | None = Field(default=1_048_576, gt=0)
    nofile: int | None = Field(default=None, gt=0)
    nproc: int | None = Field(default=64, gt=0)
    skip_limits: bool = False

    @classmethod
    def from_runtime_policy(
        cls,
        policy: WorkerRuntimePolicy,
        *,
        timeout_seconds: float,
        stdin_limit_bytes: int = 1_048_576,
        stdout_limit_bytes: int = 1_048_576,
        skip_limits: bool = False,
    ) -> "JsonWorkerExecutionConfig":
        return cls(
            stdin_limit_bytes=stdin_limit_bytes,
            stdout_limit_bytes=stdout_limit_bytes,
            cpu_seconds=max(1, math.ceil(timeout_seconds)),
            memory_bytes=parse_byte_size(policy.memory),
            file_bytes=policy.fsize_bytes,
            nofile=policy.nofile,
            nproc=policy.nproc,
            skip_limits=skip_limits,
        )

    @classmethod
    def from_env(
        cls,
        *,
        prefix: str = DEFAULT_WORKER_ENV_PREFIX,
        environ: Mapping[str, str] | None = None,
    ) -> "JsonWorkerExecutionConfig":
        return cls().with_env_overrides(prefix=prefix, environ=environ)

    def with_env_overrides(
        self,
        *,
        prefix: str = DEFAULT_WORKER_ENV_PREFIX,
        environ: Mapping[str, str] | None = None,
    ) -> "JsonWorkerExecutionConfig":
        env = environ or os.environ
        return self.model_copy(
            update={
                "stdin_limit_bytes": _parse_byte_size_env(
                    env,
                    f"{prefix}MAX_STDIN_BYTES",
                    self.stdin_limit_bytes,
                ),
                "stdout_limit_bytes": _parse_byte_size_env(
                    env,
                    f"{prefix}MAX_STDOUT_BYTES",
                    self.stdout_limit_bytes,
                ),
                "cpu_seconds": _parse_int_env(
                    env,
                    f"{prefix}CPU_SECONDS",
                    self.cpu_seconds,
                ),
                "memory_bytes": _parse_byte_size_env(
                    env,
                    f"{prefix}MEMORY_BYTES",
                    self.memory_bytes,
                ),
                "file_bytes": _parse_byte_size_env(
                    env,
                    f"{prefix}FILE_BYTES",
                    self.file_bytes,
                ),
                "nofile": _parse_int_env(
                    env,
                    f"{prefix}NOFILE",
                    self.nofile,
                ),
                "nproc": _parse_int_env(env, f"{prefix}NPROC", self.nproc),
                "skip_limits": _parse_bool_env(
                    env,
                    f"{prefix}SKIP_LIMITS",
                    self.skip_limits,
                ),
            }
        )

    def to_env(
        self,
        *,
        prefix: str = DEFAULT_WORKER_ENV_PREFIX,
    ) -> dict[str, str]:
        env = {
            f"{prefix}IN_CONTAINER": "1",
            f"{prefix}MAX_STDIN_BYTES": str(self.stdin_limit_bytes),
            f"{prefix}MAX_STDOUT_BYTES": str(self.stdout_limit_bytes),
            f"{prefix}CPU_SECONDS": str(self.cpu_seconds),
            f"{prefix}MEMORY_BYTES": str(self.memory_bytes),
            f"{prefix}SKIP_LIMITS": "true" if self.skip_limits else "false",
        }
        if self.file_bytes is not None:
            env[f"{prefix}FILE_BYTES"] = str(self.file_bytes)
        if self.nofile is not None:
            env[f"{prefix}NOFILE"] = str(self.nofile)
        if self.nproc is not None:
            env[f"{prefix}NPROC"] = str(self.nproc)
        return env

    def apply_resource_limits(self, *, skip_cpu: bool = False) -> None:
        apply_resource_limits(
            cpu_seconds=self.cpu_seconds,
            memory_bytes=self.memory_bytes,
            file_bytes=self.file_bytes,
            nofile=self.nofile,
            nproc=self.nproc,
            skip_cpu=skip_cpu or self.skip_limits,
        )


def read_stdin_bounded(
    max_bytes: int,
    *,
    stream: TextIO | None = None,
) -> str:
    """Read at most ``max_bytes`` from stdin and decode it as UTF-8."""

    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")

    source = stream or sys.stdin
    buffer = getattr(source, "buffer", None)
    if buffer is not None:
        raw_bytes = buffer.read(max_bytes + 1)
    else:
        raw_bytes = source.read(max_bytes + 1).encode("utf-8")

    actual_bytes = len(raw_bytes)
    if actual_bytes > max_bytes:
        raise OversizedPayloadError(max_bytes=max_bytes, actual_bytes=actual_bytes)
    return raw_bytes.decode("utf-8")


def load_json_stdin(
    max_bytes: int,
    *,
    stream: TextIO | None = None,
) -> Any:
    """Load a JSON payload from bounded stdin."""

    return json.loads(read_stdin_bounded(max_bytes=max_bytes, stream=stream))


def is_running_in_container() -> bool:
    """Best-effort container detection for worker self-checks."""

    if os.path.exists("/.dockerenv"):
        return True

    cgroup_paths = ("/proc/1/cgroup", "/proc/self/cgroup")
    for cgroup_path in cgroup_paths:
        try:
            with open(cgroup_path, encoding="utf-8") as handle:
                content = handle.read()
        except OSError:
            continue
        if any(marker in content for marker in ("docker", "containerd", "kubepods")):
            return True
    return False


def require_container_execution(
    *,
    flag_env_var: str | None = None,
    expected_value: str = "1",
) -> None:
    """Require a worker to run inside a container, optionally behind a runner flag."""

    if flag_env_var is not None and os.getenv(flag_env_var) != expected_value:
        raise DockerOnlyExecutionError(
            f"worker requires {flag_env_var}={expected_value} from the container runner"
        )
    if not is_running_in_container():
        raise DockerOnlyExecutionError("worker must run inside a container")


def _apply_single_rlimit(limit_name: int, value: int) -> None:
    _current_soft, current_hard = resource.getrlimit(limit_name)
    if current_hard == resource.RLIM_INFINITY:
        target_soft = value
        target_hard = value
    else:
        target_soft = min(value, current_hard)
        target_hard = min(value, current_hard)
    try:
        resource.setrlimit(limit_name, (target_soft, target_hard))
    except (OSError, ValueError) as exc:
        LOGGER.error(
            "Failed to apply resource limit %s=%s/%s: %s",
            limit_name,
            target_soft,
            target_hard,
            exc,
        )
        raise RuntimeError(
            f"failed to apply resource limit {limit_name}={target_soft}/{target_hard}"
        ) from exc


def apply_resource_limits(
    *,
    cpu_seconds: int | None = None,
    memory_bytes: int | None = None,
    file_bytes: int | None = None,
    nofile: int | None = None,
    nproc: int | None = None,
    skip_cpu: bool = False,
) -> None:
    """Apply common RLIMIT guards for JSON-over-stdin workers."""

    limits: list[tuple[int, int]] = []
    if cpu_seconds is not None and not skip_cpu:
        limits.append((resource.RLIMIT_CPU, cpu_seconds))
    if memory_bytes is not None:
        limits.append((resource.RLIMIT_AS, memory_bytes))
    if file_bytes is not None:
        limits.append((resource.RLIMIT_FSIZE, file_bytes))
    if nofile is not None:
        limits.append((resource.RLIMIT_NOFILE, nofile))
    if nproc is not None:
        limits.append((resource.RLIMIT_NPROC, nproc))

    for limit_name, value in limits:
        if value <= 0:
            raise ValueError("resource limit values must be positive")
        _apply_single_rlimit(limit_name, value)
