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

        try:
            completed = subprocess.run(
                request.command,
                check=False,
                capture_output=True,
                text=True,
                timeout=request.timeout_seconds,
                cwd=request.working_dir,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            duration = time.monotonic() - start
            return DockerRuntimeResult(
                ok=False,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
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
            ok=completed.returncode == 0,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_seconds=duration,
        )
