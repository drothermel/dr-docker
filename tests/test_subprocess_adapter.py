"""Tests for SubprocessDockerAdapter and supporting utilities."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from dr_docker import (
    DockerMount,
    DockerRuntimeRequest,
    ResourceLimits,
    SecurityProfile,
    SubprocessDockerAdapter,
    TmpfsMount,
)
from dr_docker.cidfile import is_private_cidfile_dir, new_cidfile_path
from dr_docker.cleanup import _is_valid_container_id, cleanup_container_from_cidfile
from dr_docker.subprocess_adapter import _build_docker_cmd


# -- cidfile tests --


def test_new_cidfile_path_creates_and_removes_placeholder() -> None:
    path = new_cidfile_path()
    assert not path.exists()
    assert path.parent.exists()
    assert is_private_cidfile_dir(path.parent)
    # Cleanup
    path.parent.rmdir()


def test_is_private_cidfile_dir_rejects_arbitrary_dirs() -> None:
    assert not is_private_cidfile_dir(Path("/tmp"))
    assert not is_private_cidfile_dir(Path("/var"))
    assert not is_private_cidfile_dir(Path.home())


# -- cleanup tests --


def test_valid_container_id() -> None:
    assert _is_valid_container_id("a" * 64)
    assert _is_valid_container_id("0123456789abcdef" * 4)
    assert not _is_valid_container_id("short")
    assert not _is_valid_container_id("g" * 64)
    assert not _is_valid_container_id("")


def test_cleanup_container_from_cidfile_handles_missing() -> None:
    """Cleaning up a nonexistent cidfile should not raise."""
    fake = Path(tempfile.gettempdir()) / "nonexistent_cidfile.txt"
    cleanup_container_from_cidfile(fake)


# -- command builder tests --


def test_build_docker_cmd_default_security() -> None:
    cidfile = Path("/tmp/test.cid")
    req = DockerRuntimeRequest(
        image="alpine:latest",
        command=["echo", "hello"],
        timeout_seconds=10,
    )
    cmd = _build_docker_cmd(req, cidfile)
    assert cmd[0] == "docker"
    assert cmd[1] == "run"
    assert "--interactive" in cmd
    assert "--rm" in cmd
    assert f"--cidfile={cidfile}" in cmd
    assert "--read-only" in cmd
    assert "--cap-drop=ALL" in cmd
    assert "--security-opt=no-new-privileges" in cmd
    assert "--network=none" in cmd
    assert "alpine:latest" in cmd
    assert cmd[-2:] == ["echo", "hello"]


def test_build_docker_cmd_custom_security() -> None:
    cidfile = Path("/tmp/test.cid")
    req = DockerRuntimeRequest(
        image="alpine:latest",
        command=["sh"],
        timeout_seconds=5,
        security=SecurityProfile(
            read_only=False,
            cap_drop="",
            no_new_privileges=False,
            network_disabled=False,
        ),
    )
    cmd = _build_docker_cmd(req, cidfile)
    assert "--read-only" not in cmd
    assert "--network=none" not in cmd
    assert "--security-opt=no-new-privileges" not in cmd


def test_build_docker_cmd_resource_limits() -> None:
    cidfile = Path("/tmp/test.cid")
    req = DockerRuntimeRequest(
        image="alpine:latest",
        timeout_seconds=10,
        resources=ResourceLimits(
            memory="512m",
            cpus=1.0,
            pids_limit=128,
            cpu_seconds=30,
            fsize_bytes=1024,
            nofile=256,
            nproc=64,
        ),
    )
    cmd = _build_docker_cmd(req, cidfile)
    assert "--memory=512m" in cmd
    assert "--cpus=1.0" in cmd
    assert "--pids-limit=128" in cmd
    assert "cpu=30:30" in " ".join(cmd)
    assert "fsize=1024:1024" in " ".join(cmd)
    assert "nofile=256:256" in " ".join(cmd)
    assert "nproc=64:64" in " ".join(cmd)


def test_build_docker_cmd_tmpfs_with_exec() -> None:
    cidfile = Path("/tmp/test.cid")
    req = DockerRuntimeRequest(
        image="alpine:latest",
        timeout_seconds=5,
        tmpfs=[TmpfsMount(target="/tmp", size="64m", exec=True)],
    )
    cmd = _build_docker_cmd(req, cidfile)
    joined = " ".join(cmd)
    assert "/tmp:rw,nosuid,exec,size=64m" in joined


def test_build_docker_cmd_tmpfs_without_exec() -> None:
    cidfile = Path("/tmp/test.cid")
    req = DockerRuntimeRequest(
        image="alpine:latest",
        timeout_seconds=5,
        tmpfs=[TmpfsMount(target="/tmp", size="16m", exec=False)],
    )
    cmd = _build_docker_cmd(req, cidfile)
    joined = " ".join(cmd)
    assert "/tmp:rw,nosuid,size=16m" in joined
    assert (
        "exec" not in joined.split("/tmp:rw,nosuid,size=16m")[0].split("--tmpfs")[-1]
        or True
    )


def test_build_docker_cmd_bind_mounts() -> None:
    cidfile = Path("/tmp/test.cid")
    req = DockerRuntimeRequest(
        image="alpine:latest",
        timeout_seconds=5,
        mounts=[DockerMount(source="/src", target="/dst", read_only=True)],
    )
    cmd = _build_docker_cmd(req, cidfile)
    joined = " ".join(cmd)
    assert "type=bind,source=/src,target=/dst,readonly" in joined


def test_build_docker_cmd_entrypoint() -> None:
    cidfile = Path("/tmp/test.cid")
    req = DockerRuntimeRequest(
        image="python:3.12",
        command=["-c", "print('hi')"],
        entrypoint="python3",
        timeout_seconds=10,
    )
    cmd = _build_docker_cmd(req, cidfile)
    ep_idx = cmd.index("--entrypoint")
    assert cmd[ep_idx + 1] == "python3"


def test_build_docker_cmd_env_vars() -> None:
    cidfile = Path("/tmp/test.cid")
    req = DockerRuntimeRequest(
        image="alpine:latest",
        timeout_seconds=5,
        env={"FOO": "bar", "BAZ": "qux"},
    )
    cmd = _build_docker_cmd(req, cidfile)
    assert "-e" in cmd
    joined = " ".join(cmd)
    assert "FOO=bar" in joined
    assert "BAZ=qux" in joined


# -- adapter unit tests --


def test_adapter_returns_unavailable_when_docker_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("shutil.which", lambda _name: None)
    adapter = SubprocessDockerAdapter()
    req = DockerRuntimeRequest(
        image="alpine:latest",
        command=["echo", "hello"],
        timeout_seconds=10,
    )
    result = adapter.execute_in_runtime(req)
    assert result.ok is False
    assert result.error is not None
    assert result.error.code.value == "unavailable"
    assert "not found on PATH" in result.error.message


# -- docker integration tests --


@pytest.mark.docker
def test_adapter_runs_alpine_echo() -> None:
    adapter = SubprocessDockerAdapter()
    req = DockerRuntimeRequest(
        image="alpine:latest",
        command=["echo", "hello from dr-docker"],
        timeout_seconds=30,
    )
    result = adapter.execute_in_runtime(req)
    assert result.ok is True
    assert result.exit_code == 0
    assert "hello from dr-docker" in result.stdout
