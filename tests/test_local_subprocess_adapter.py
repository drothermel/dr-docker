import sys

from nl_runtime_primitives import (
    DockerRuntimeRequest,
    ErrorCode,
    LocalSubprocessRuntimeAdapter,
    RuntimeAdapter,
)


def test_local_subprocess_adapter_is_runtime_adapter_protocol() -> None:
    adapter = LocalSubprocessRuntimeAdapter()
    assert isinstance(adapter, RuntimeAdapter)


def test_local_subprocess_executes_command() -> None:
    adapter = LocalSubprocessRuntimeAdapter()
    result = adapter.execute_in_runtime(
        DockerRuntimeRequest(
            image="python:3.12-slim",
            command=[sys.executable, "-c", "print('ok')"],
            timeout_seconds=5,
        )
    )

    assert result.ok is True
    assert result.exit_code == 0
    assert result.stdout.strip() == "ok"
    assert result.error is None


def test_local_subprocess_reports_timeout() -> None:
    adapter = LocalSubprocessRuntimeAdapter()
    result = adapter.execute_in_runtime(
        DockerRuntimeRequest(
            image="python:3.12-slim",
            command=[
                sys.executable,
                "-c",
                "import sys,time; print('before-timeout', flush=True); "
                "print('err-before-timeout', file=sys.stderr); time.sleep(2)",
            ],
            timeout_seconds=1,
        )
    )

    assert result.ok is False
    assert result.exit_code is None
    assert result.error is not None
    assert result.error.code == ErrorCode.TIMEOUT
    assert result.error.details.get("timeout_seconds") == 1
    assert "before-timeout" in result.stdout
    assert "err-before-timeout" in result.stderr


def test_local_subprocess_passes_env_vars() -> None:
    adapter = LocalSubprocessRuntimeAdapter()
    result = adapter.execute_in_runtime(
        DockerRuntimeRequest(
            image="python:3.12-slim",
            command=[sys.executable, "-c", "import os; print(os.getenv('FOO', ''))"],
            env={"FOO": "bar"},
            timeout_seconds=5,
        )
    )

    assert result.ok is True
    assert result.stdout.strip() == "bar"
