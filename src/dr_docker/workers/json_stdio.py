"""Optional helpers for JSON-over-stdin workers running inside containers."""

from __future__ import annotations

import json
import logging
import os
import resource
import sys
from typing import Any, TextIO

LOGGER = logging.getLogger(__name__)


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
            "failed to apply resource limit "
            f"{limit_name}={target_soft}/{target_hard}"
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
