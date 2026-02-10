"""Concrete local runtime adapter backed by subprocess execution."""

from __future__ import annotations

import os
import subprocess
import time

from .docker_contract import DockerRuntimeRequest, DockerRuntimeResult
from .errors import ErrorCode, ErrorEnvelope


def _timeout_output(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    if isinstance(value, str):
        return value
    return ""


class LocalSubprocessRuntimeAdapter:
    """Runtime adapter that executes request commands on the local host."""

    def execute_in_runtime(
        self, request: DockerRuntimeRequest
    ) -> DockerRuntimeResult:
        if not request.command:
            return DockerRuntimeResult(
                ok=False,
                error=ErrorEnvelope(
                    code=ErrorCode.MALFORMED_REQUEST,
                    message="command must not be empty",
                    details={"field": "command"},
                ),
            )

        start = time.monotonic()
        env = os.environ.copy()
        env.update(request.env)
        process: subprocess.Popen[str] | None = None

        try:
            process = subprocess.Popen(
                request.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=request.working_dir,
                env=env,
            )
            stdout, stderr = process.communicate(timeout=request.timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            if process is not None:
                process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                try:
                    out, err = process.communicate(timeout=1)
                    stdout = out or ""
                    stderr = err or ""
                except subprocess.TimeoutExpired as final_exc:
                    stdout = _timeout_output(final_exc.stdout) or _timeout_output(
                        exc.stdout
                    )
                    stderr = _timeout_output(final_exc.stderr) or _timeout_output(
                        exc.stderr
                    )
            else:
                stdout = _timeout_output(exc.stdout)
                stderr = _timeout_output(exc.stderr)
            duration = time.monotonic() - start
            return DockerRuntimeResult(
                ok=False,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=duration,
                error=ErrorEnvelope(
                    code=ErrorCode.TIMEOUT,
                    message=f"command timed out after {request.timeout_seconds} seconds",
                    retriable=True,
                    details={"timeout_seconds": request.timeout_seconds},
                ),
            )
        except OSError as exc:
            duration = time.monotonic() - start
            return DockerRuntimeResult(
                ok=False,
                duration_seconds=duration,
                error=ErrorEnvelope(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=f"subprocess execution failed: {exc}",
                    retriable=False,
                ),
            )
        except ValueError as exc:
            duration = time.monotonic() - start
            return DockerRuntimeResult(
                ok=False,
                duration_seconds=duration,
                error=ErrorEnvelope(
                    code=ErrorCode.MALFORMED_REQUEST,
                    message=f"invalid subprocess request: {exc}",
                    retriable=False,
                    details={"field": "command"},
                ),
            )

        duration = time.monotonic() - start
        exit_code = process.returncode
        if exit_code != 0:
            return DockerRuntimeResult(
                ok=False,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=duration,
                error=ErrorEnvelope(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=f"command exited with code {exit_code}",
                    retriable=False,
                    details={"exit_code": exit_code},
                ),
            )
        return DockerRuntimeResult(
            ok=True,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration,
        )
