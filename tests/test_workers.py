from __future__ import annotations

import io
import resource
from pathlib import Path

import pytest

from dr_docker import (
    DockerMount,
    JsonWorkerExecutionConfig,
    TmpfsMount,
    WorkerRuntimePolicy,
    build_mounted_worker_request,
    mount_worker_directory,
    mount_worker_file,
    parse_byte_size,
)
from dr_docker.subprocess_adapter import _build_docker_cmd
from dr_docker.workers.json_stdio import (
    DEFAULT_WORKER_IN_CONTAINER_ENV_VAR,
    BoundedTextCapture,
    DockerOnlyExecutionError,
    OversizedPayloadError,
    apply_resource_limits,
    load_json_stdin,
    read_stdin_bounded,
    require_container_execution,
)


def test_worker_runtime_policy_defaults_and_overrides() -> None:
    policy = WorkerRuntimePolicy.small_isolated()
    assert policy.memory == "512m"
    assert policy.cpus == 1.0
    assert policy.pids_limit == 256
    assert policy.tmpfs_size == "64m"
    assert policy.tmpfs_target == "/tmp"
    assert policy.tmpfs_exec is False
    assert policy.fsize_bytes == 10_485_760
    assert policy.nofile == 1024
    assert policy.nproc == 256

    overridden = policy.model_copy(
        update={
            "memory": "1g",
            "tmpfs_exec": True,
            "nproc": 32,
        }
    )
    limits = overridden.to_resource_limits()
    tmpfs = overridden.to_tmpfs_mounts()

    assert limits.memory == "1g"
    assert limits.nproc == 32
    assert tmpfs == [TmpfsMount(target="/tmp", size="64m", exec_=True)]


def test_parse_byte_size_supports_integers_suffixes_and_decimals() -> None:
    assert parse_byte_size("1024") == 1024
    assert parse_byte_size("1k") == 1024
    assert parse_byte_size("2M") == 2 * 1024**2
    assert parse_byte_size("1.5g") == int(1.5 * 1024**3)
    assert parse_byte_size(" 64m ") == 64 * 1024**2

    with pytest.raises(ValueError):
        parse_byte_size("bogus")


def test_worker_runtime_policy_with_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DR_DOCKER_MEMORY", "2g")
    monkeypatch.setenv("DR_DOCKER_CPUS", "1.5")
    monkeypatch.setenv("DR_DOCKER_PIDS_LIMIT", "128")
    monkeypatch.setenv("DR_DOCKER_TMPFS_SIZE", "32m")
    monkeypatch.setenv("DR_DOCKER_TMPFS_EXEC", "true")
    monkeypatch.setenv("DR_DOCKER_FSIZE_BYTES", "4096")
    monkeypatch.setenv("DR_DOCKER_NOFILE", "256")

    policy = WorkerRuntimePolicy.small_isolated().with_env_overrides()

    assert policy.memory == "2g"
    assert policy.cpus == 1.5
    assert policy.pids_limit == 128
    assert policy.tmpfs_size == "32m"
    assert policy.tmpfs_exec is True
    assert policy.fsize_bytes == 4096
    assert policy.nofile == 256
    assert policy.nproc == 128

    monkeypatch.setenv("DR_DOCKER_NPROC", "12")
    explicit_nproc = WorkerRuntimePolicy.small_isolated().with_env_overrides()
    assert explicit_nproc.nproc == 12

    monkeypatch.setenv("CUSTOM_MEMORY", "3g")
    custom_prefix_policy = WorkerRuntimePolicy.small_isolated().with_env_overrides(
        prefix="CUSTOM_"
    )
    assert custom_prefix_policy.memory == "3g"

    with pytest.raises(ValueError, match="DR_DOCKER_CPUS"):
        WorkerRuntimePolicy.small_isolated().with_env_overrides(
            environ={"DR_DOCKER_CPUS": "oops"}
        )


def test_worker_runtime_policy_with_env_overrides_preserves_explicit_empty_environ() -> None:
    policy = WorkerRuntimePolicy.small_isolated().with_env_overrides(environ={})
    assert policy == WorkerRuntimePolicy.small_isolated()


def test_mount_worker_file_builds_request_with_policy_and_stdin(
    tmp_path: Path,
) -> None:
    worker_source = tmp_path / "worker.py"
    worker_source.write_text("print('worker')\n", encoding="utf-8")

    worker = mount_worker_file(
        worker_source, mount_target="/sandbox"
    ).with_path_command(
        entrypoint="python3",
        args_before_path=["-I"],
        working_dir="/tmp",
    )
    policy = WorkerRuntimePolicy.small_isolated().model_copy(
        update={"memory": "768m", "tmpfs_exec": True}
    )
    request = build_mounted_worker_request(
        image="python:3.12-slim",
        worker=worker,
        timeout_seconds=15,
        policy=policy,
        stdin_payload='{"ping": true}',
        env={"WORKER_MODE": "json"},
    )

    assert request.image == "python:3.12-slim"
    assert request.entrypoint == "python3"
    assert request.command == ["-I", "/sandbox/worker.py"]
    assert request.working_dir == "/tmp"
    assert request.stdin_payload == b'{"ping": true}'
    assert request.env == {"WORKER_MODE": "json"}
    assert request.mounts == [
        DockerMount(
            source=str(worker_source.parent.resolve()),
            target="/sandbox",
            read_only=True,
        )
    ]
    assert request.tmpfs == [TmpfsMount(target="/tmp", size="64m", exec_=True)]
    assert request.resources.memory == "768m"

    cmd = _build_docker_cmd(request, Path("/tmp/test.cid"))
    joined = " ".join(cmd)
    assert "--entrypoint" in cmd
    assert "type=bind,source=" in joined
    assert "target=/sandbox,readonly" in joined
    assert "/tmp:rw,nosuid,exec,size=64m" in joined
    assert "WORKER_MODE=json" in joined
    assert cmd[-2:] == ["-I", "/sandbox/worker.py"]


def test_mount_worker_directory_supports_relative_worker_path_and_extra_wiring(
    tmp_path: Path,
) -> None:
    worker_dir = tmp_path / "worker"
    worker_dir.mkdir()
    (worker_dir / "bin").mkdir()
    (worker_dir / "bin" / "worker.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    worker = mount_worker_directory(
        worker_dir,
        mount_target="/opt/worker",
        relative_path="bin/worker.sh",
    ).with_path_command(entrypoint="sh", working_dir="/work")

    request = build_mounted_worker_request(
        image="alpine:latest",
        worker=worker,
        timeout_seconds=20,
        extra_mounts=[DockerMount(source=str(data_dir), target="/data")],
        extra_tmpfs=[TmpfsMount(target="/scratch", size="8m", exec_=False)],
        env={"EXTRA_FLAG": "1"},
    )

    assert request.command == ["/opt/worker/bin/worker.sh"]
    assert request.working_dir == "/work"
    assert request.env == {"EXTRA_FLAG": "1"}
    assert request.mounts[0].target == "/opt/worker"
    assert request.mounts[1] == DockerMount(source=str(data_dir), target="/data")
    assert request.tmpfs == [
        TmpfsMount(target="/tmp", size="64m", exec_=False),
        TmpfsMount(target="/scratch", size="8m", exec_=False),
    ]


def test_with_path_command_preserves_existing_entrypoint(tmp_path: Path) -> None:
    worker_source = tmp_path / "worker.py"
    worker_source.write_text("print('worker')\n", encoding="utf-8")

    worker = mount_worker_file(worker_source).with_path_command(entrypoint="python3")
    updated_worker = worker.with_path_command(args_before_path=["-I"])

    assert updated_worker.entrypoint == "python3"
    assert updated_worker.command == ["-I", "/worker/worker.py"]


def test_mount_worker_directory_rejects_escape_relative_path(tmp_path: Path) -> None:
    worker_dir = tmp_path / "worker"
    worker_dir.mkdir()

    with pytest.raises(ValueError, match="must not escape"):
        mount_worker_directory(worker_dir, relative_path="../outside.py")


def test_read_stdin_bounded_and_load_json() -> None:
    stream = io.TextIOWrapper(io.BytesIO(b'{"value": 3}'), encoding="utf-8")
    assert read_stdin_bounded(32, stream=stream) == '{"value": 3}'

    json_stream = io.TextIOWrapper(io.BytesIO(b'{"value": 7}'), encoding="utf-8")
    assert load_json_stdin(32, stream=json_stream) == {"value": 7}


def test_read_stdin_bounded_rejects_oversized_payload() -> None:
    stream = io.TextIOWrapper(io.BytesIO(b"abcdef"), encoding="utf-8")
    with pytest.raises(OversizedPayloadError) as exc_info:
        read_stdin_bounded(4, stream=stream)
    assert exc_info.value.max_bytes == 4
    assert exc_info.value.actual_bytes == 5


def test_bounded_text_capture_truncates_utf8_output() -> None:
    capture = BoundedTextCapture(limit_bytes=5)
    capture.write("ab")
    capture.write("cdef")
    capture.write("ghi")

    assert capture.getvalue() == "abcde"
    assert capture.truncated is True


def test_require_container_execution_honors_runner_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "dr_docker.workers.json_stdio.is_running_in_container",
        lambda: True,
    )
    monkeypatch.setenv(DEFAULT_WORKER_IN_CONTAINER_ENV_VAR, "1")
    require_container_execution(flag_env_var=DEFAULT_WORKER_IN_CONTAINER_ENV_VAR)

    monkeypatch.setenv(DEFAULT_WORKER_IN_CONTAINER_ENV_VAR, "0")
    with pytest.raises(
        DockerOnlyExecutionError, match=DEFAULT_WORKER_IN_CONTAINER_ENV_VAR
    ):
        require_container_execution(flag_env_var=DEFAULT_WORKER_IN_CONTAINER_ENV_VAR)


def test_apply_resource_limits_uses_positive_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    applied: list[tuple[int, tuple[int, int]]] = []
    infinity = 10_000

    monkeypatch.setattr(
        "dr_docker.workers.json_stdio.resource.getrlimit",
        lambda _limit_name: (0, infinity),
    )
    monkeypatch.setattr(
        "dr_docker.workers.json_stdio.resource.setrlimit",
        lambda limit_name, value: applied.append((limit_name, value)),
    )

    apply_resource_limits(
        cpu_seconds=3,
        memory_bytes=1024,
        file_bytes=2048,
        nofile=32,
        nproc=16,
    )

    assert len(applied) == 5
    assert all(soft == hard for _limit_name, (soft, hard) in applied)

    with pytest.raises(ValueError, match="positive"):
        apply_resource_limits(memory_bytes=0)


def test_apply_resource_limits_raises_when_rlimit_application_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "dr_docker.workers.json_stdio.resource.getrlimit",
        lambda _limit_name: (0, resource.RLIM_INFINITY),
    )

    def _raise_setrlimit(_limit_name: int, _value: tuple[int, int]) -> None:
        raise OSError("permission denied")

    monkeypatch.setattr(
        "dr_docker.workers.json_stdio.resource.setrlimit",
        _raise_setrlimit,
    )

    with pytest.raises(RuntimeError, match="failed to apply resource limit"):
        apply_resource_limits(memory_bytes=1024)


def test_json_worker_execution_config_round_trips_and_applies_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = JsonWorkerExecutionConfig.from_runtime_policy(
        WorkerRuntimePolicy.small_isolated().model_copy(
            update={"memory": "1.5g", "fsize_bytes": 8192, "nofile": 64, "nproc": 32}
        ),
        timeout_seconds=2.2,
        stdin_limit_bytes=4096,
        stdout_limit_bytes=8192,
    )

    assert config.memory_bytes == int(1.5 * 1024**3)
    assert config.cpu_seconds == 3
    assert config.file_bytes == 8192
    assert config.nofile == 64
    assert config.nproc == 32

    env = config.to_env()
    round_tripped = JsonWorkerExecutionConfig.from_env(environ=env)
    assert round_tripped == config

    monkeypatch.setenv("DR_DOCKER_WORKER_MEMORY_BYTES", "2g")
    monkeypatch.setenv("DR_DOCKER_WORKER_MAX_STDOUT_BYTES", "16k")
    monkeypatch.setenv("DR_DOCKER_WORKER_SKIP_LIMITS", "yes")
    overridden = config.with_env_overrides()
    assert overridden.memory_bytes == 2 * 1024**3
    assert overridden.stdout_limit_bytes == 16 * 1024
    assert overridden.skip_limits is True

    with pytest.raises(ValueError, match="DR_DOCKER_WORKER_MEMORY_BYTES"):
        config.with_env_overrides(environ={"DR_DOCKER_WORKER_MEMORY_BYTES": "bad"})


def test_json_worker_execution_config_with_env_overrides_preserves_explicit_empty_environ() -> None:
    config = JsonWorkerExecutionConfig()
    assert config.with_env_overrides(environ={}) == config


def test_json_worker_execution_config_apply_resource_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    applied: list[dict[str, int | None | bool]] = []

    monkeypatch.setattr(
        "dr_docker.workers.json_stdio.apply_resource_limits",
        lambda **kwargs: applied.append(kwargs),
    )

    config = JsonWorkerExecutionConfig(
        stdin_limit_bytes=1024,
        stdout_limit_bytes=1024,
        cpu_seconds=5,
        memory_bytes=4096,
        file_bytes=2048,
        nofile=32,
        nproc=16,
        skip_limits=False,
    )
    config.apply_resource_limits(skip_cpu=True)

    assert applied == [
        {
            "cpu_seconds": 5,
            "memory_bytes": 4096,
            "file_bytes": 2048,
            "nofile": 32,
            "nproc": 16,
            "skip_cpu": True,
        }
    ]
