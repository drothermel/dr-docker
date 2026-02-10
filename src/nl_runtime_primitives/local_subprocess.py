"""Concrete local runtime adapter backed by subprocess execution."""

from __future__ import annotations

import os
import subprocess
import time

from .docker_contract import DockerRuntimeRequest, DockerRuntimeResult
from .errors import ErrorCode, ErrorEnvelope


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
                out, err = process.communicate()
                stdout = out or ""
                stderr = err or ""
            else:
                stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
                stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
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

        duration = time.monotonic() - start
        return DockerRuntimeResult(
            ok=process.returncode == 0,
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration,
        )
