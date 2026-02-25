"""Concrete RuntimeAdapter using subprocess + Docker CLI."""

from __future__ import annotations

import logging
import math
import os
import selectors
import shutil
import subprocess
import time
from contextlib import suppress
from pathlib import Path
from threading import Thread
from typing import BinaryIO

from .cidfile import new_cidfile_path
from .cleanup import cleanup_container_from_cidfile
from .docker_contract import (
    DockerRuntimeRequest,
    DockerRuntimeResult,
)
from .errors import ErrorCode, ErrorEnvelope

_LOGGER = logging.getLogger(__name__)


def _build_docker_cmd(
    request: DockerRuntimeRequest,
    cidfile: Path,
) -> list[str]:
    """Translate a DockerRuntimeRequest into docker run CLI args."""
    sec = request.security
    res = request.resources

    cmd: list[str] = [
        "docker",
        "run",
        "--interactive",
        "--rm",
        f"--cidfile={cidfile}",
    ]

    if request.entrypoint is not None:
        cmd.extend(["--entrypoint", request.entrypoint])

    # Security profile
    if sec.read_only:
        cmd.append("--read-only")
    if sec.cap_drop:
        cmd.append(f"--cap-drop={sec.cap_drop}")
    if sec.no_new_privileges:
        cmd.append("--security-opt=no-new-privileges")
    if sec.network_disabled:
        cmd.append("--network=none")

    # Resource limits
    cmd.append(f"--memory={res.memory}")
    cmd.append(f"--cpus={res.cpus}")
    cmd.append(f"--pids-limit={res.pids_limit}")
    if res.cpu_seconds is not None:
        cmd.extend(["--ulimit", f"cpu={res.cpu_seconds}:{res.cpu_seconds}"])
    if res.fsize_bytes is not None:
        cmd.extend(["--ulimit", f"fsize={res.fsize_bytes}:{res.fsize_bytes}"])
    if res.nofile is not None:
        cmd.extend(["--ulimit", f"nofile={res.nofile}:{res.nofile}"])
    if res.nproc is not None:
        cmd.extend(["--ulimit", f"nproc={res.nproc}:{res.nproc}"])

    # Tmpfs mounts
    for tmpfs in request.tmpfs:
        exec_flag = ",exec" if tmpfs.exec_ else ""
        opts = f"{tmpfs.target}:rw,nosuid{exec_flag},size={tmpfs.size}"
        cmd.extend(["--tmpfs", opts])

    # Bind mounts
    for mount in request.mounts:
        ro = ",readonly" if mount.read_only else ""
        cmd.extend(
            [
                "--mount",
                f"type=bind,source={mount.source},target={mount.target}{ro}",
            ]
        )

    # Environment
    for key, value in request.env.items():
        cmd.extend(["-e", f"{key}={value}"])

    # Working directory
    if request.working_dir is not None:
        cmd.extend(["-w", request.working_dir])

    # Image + command
    cmd.append(request.image)
    cmd.extend(request.command)

    return cmd


def _collect_capped_process_output(
    proc: subprocess.Popen[bytes],
    *,
    cmd: list[str],
    timeout_seconds: float,
    stdout_limit: int,
    stderr_limit: int,
) -> tuple[int, str, str]:
    """Selector-based concurrent stdout/stderr reader with byte caps."""
    stdout = proc.stdout
    stderr = proc.stderr
    if stdout is None or stderr is None:
        missing = []
        if stdout is None:
            missing.append("stdout")
        if stderr is None:
            missing.append("stderr")
        raise RuntimeError(
            f"Missing subprocess {' and '.join(missing)} pipe(s) for command: {cmd!r}"
        )

    stream_buffers: dict[int, bytearray] = {
        stdout.fileno(): bytearray(),
        stderr.fileno(): bytearray(),
    }
    stream_limits = {
        stdout.fileno(): stdout_limit,
        stderr.fileno(): stderr_limit,
    }
    stream_totals = {
        stdout.fileno(): 0,
        stderr.fileno(): 0,
    }
    stream_truncated = {
        stdout.fileno(): False,
        stderr.fileno(): False,
    }

    with selectors.DefaultSelector() as selector:
        selector.register(stdout, selectors.EVENT_READ)
        selector.register(stderr, selectors.EVENT_READ)
        start = time.monotonic()

        while selector.get_map():
            remaining = timeout_seconds - (time.monotonic() - start)
            if remaining <= 0:
                proc.kill()
                proc.wait()
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout_seconds)
            events = selector.select(timeout=remaining)
            for key, _ in events:
                chunk = os.read(key.fd, 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                stream_totals[key.fd] += len(chunk)
                buffer = stream_buffers[key.fd]
                limit = stream_limits[key.fd]
                remaining_cap = limit - len(buffer)
                if remaining_cap > 0:
                    kept = chunk[:remaining_cap]
                    buffer.extend(kept)
                    if len(kept) < len(chunk):
                        stream_truncated[key.fd] = True
                else:
                    stream_truncated[key.fd] = True

    remaining = timeout_seconds - (time.monotonic() - start)
    if remaining <= 0:
        proc.kill()
        proc.wait()
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout_seconds)
    try:
        returncode = proc.wait(timeout=remaining)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        raise

    stdout_text = stream_buffers[stdout.fileno()].decode("utf-8", errors="replace")
    stderr_text = stream_buffers[stderr.fileno()].decode("utf-8", errors="replace")
    if stream_truncated[stdout.fileno()]:
        stdout_text += (
            "\n[stdout truncated: "
            f"{stream_totals[stdout.fileno()]} bytes total, "
            f"capped at {stdout_limit} bytes]"
        )
    if stream_truncated[stderr.fileno()]:
        stderr_text += (
            "\n[stderr truncated: "
            f"{stream_totals[stderr.fileno()]} bytes total, "
            f"capped at {stderr_limit} bytes]"
        )

    return returncode, stdout_text, stderr_text


class SubprocessDockerAdapter:
    """Execute Docker containers via subprocess with stream capping."""

    def __init__(
        self,
        *,
        max_stdout_bytes: int = 1_048_576,
        max_stderr_bytes: int = 1_048_576,
    ) -> None:
        self._max_stdout_bytes = max_stdout_bytes
        self._max_stderr_bytes = max_stderr_bytes

    def execute_in_runtime(self, request: DockerRuntimeRequest) -> DockerRuntimeResult:
        """Build docker run CLI, execute, return result."""
        if not shutil.which("docker"):
            return DockerRuntimeResult(
                ok=False,
                error=ErrorEnvelope(
                    code=ErrorCode.UNAVAILABLE,
                    message="Docker CLI not found on PATH",
                ),
            )

        # Compute cpu_seconds from timeout if not explicitly set
        resources = request.resources
        if resources.cpu_seconds is None:
            cpu_seconds = max(1, math.ceil(request.timeout_seconds))
            resources = resources.model_copy(update={"cpu_seconds": cpu_seconds})
            request = request.model_copy(update={"resources": resources})

        try:
            cidfile = new_cidfile_path()
            cmd = _build_docker_cmd(request, cidfile)
        except OSError as exc:
            return DockerRuntimeResult(
                ok=False,
                error=ErrorEnvelope(
                    code=ErrorCode.UNAVAILABLE,
                    message=f"Failed to prepare Docker runtime: {exc}",
                ),
            )
        start = time.monotonic()

        try:
            return self._run(cmd, request, cidfile, start)
        finally:
            cleanup_container_from_cidfile(cidfile)

    def _run(
        self,
        cmd: list[str],
        request: DockerRuntimeRequest,
        cidfile: Path,
        start: float,
    ) -> DockerRuntimeResult:
        try:
            with subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            ) as proc:
                stdin = proc.stdin
                if stdin is None:
                    raise RuntimeError(
                        f"Missing subprocess stdin pipe for command: {cmd!r}"
                    )

                writer = Thread(
                    target=self._write_stdin_and_close,
                    args=(stdin, request.stdin_payload),
                    daemon=True,
                )
                writer.start()
                try:
                    returncode, stdout_text, stderr_text = (
                        _collect_capped_process_output(
                            proc,
                            cmd=cmd,
                            timeout_seconds=float(request.timeout_seconds),
                            stdout_limit=self._max_stdout_bytes,
                            stderr_limit=self._max_stderr_bytes,
                        )
                    )
                finally:
                    writer.join()

            duration = time.monotonic() - start
            container_id = self._read_cidfile(cidfile)

            if returncode == 0:
                return DockerRuntimeResult(
                    ok=True,
                    exit_code=returncode,
                    stdout=stdout_text,
                    stderr=stderr_text,
                    duration_seconds=duration,
                    container_id=container_id,
                )
            return DockerRuntimeResult(
                ok=False,
                exit_code=returncode,
                stdout=stdout_text,
                stderr=stderr_text,
                duration_seconds=duration,
                container_id=container_id,
                error=ErrorEnvelope(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=f"Container exited with code {returncode}",
                ),
            )

        except subprocess.TimeoutExpired:
            duration = time.monotonic() - start
            return DockerRuntimeResult(
                ok=False,
                duration_seconds=duration,
                container_id=self._read_cidfile(cidfile),
                error=ErrorEnvelope(
                    code=ErrorCode.TIMEOUT,
                    message=(f"Container timed out after {request.timeout_seconds}s"),
                    retriable=True,
                ),
            )
        except (FileNotFoundError, OSError) as exc:
            duration = time.monotonic() - start
            return DockerRuntimeResult(
                ok=False,
                duration_seconds=duration,
                error=ErrorEnvelope(
                    code=ErrorCode.UNAVAILABLE,
                    message=f"Docker execution failed: {exc}",
                ),
            )
        except RuntimeError as exc:
            duration = time.monotonic() - start
            return DockerRuntimeResult(
                ok=False,
                duration_seconds=duration,
                error=ErrorEnvelope(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=str(exc),
                ),
            )

    @staticmethod
    def _read_cidfile(cidfile: Path) -> str | None:
        try:
            cid = cidfile.read_text(encoding="utf-8").strip()
            return cid if cid else None
        except OSError:
            return None

    @staticmethod
    def _write_stdin_and_close(
        stdin_pipe: BinaryIO,
        stdin_payload: bytes | None,
    ) -> None:
        try:
            if stdin_payload is not None:
                with suppress(BrokenPipeError):
                    stdin_pipe.write(stdin_payload)
        finally:
            with suppress(BrokenPipeError, OSError):
                stdin_pipe.close()
