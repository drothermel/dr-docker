from pathlib import Path
import re

import pytest
from pydantic import ValidationError

from dr_docker import (
    CONTRACT_VERSION,
    DockerMount,
    DockerRuntimeRequest,
    DockerRuntimeResult,
    ErrorCode,
    ErrorEnvelope,
    ResourceLimits,
    SecurityProfile,
    TmpfsMount,
    __version__,
)


def test_docker_request_and_result_model_validation_roundtrip() -> None:
    req = DockerRuntimeRequest.model_validate(
        {
            "image": "python:3.12-slim",
            "command": ["python", "-c", "print('ok')"],
            "env": {"PYTHONUNBUFFERED": "1"},
            "mounts": [{"source": "/tmp", "target": "/workspace", "read_only": True}],
            "timeout_seconds": 30,
        }
    )
    assert isinstance(req.mounts[0], DockerMount)
    req_dump = req.model_dump(mode="json")
    assert (
        DockerRuntimeRequest.model_validate(req_dump).model_dump(mode="json")
        == req_dump
    )

    with pytest.raises(ValidationError):
        DockerRuntimeRequest.model_validate({"timeout_seconds": 10})
    with pytest.raises(ValidationError):
        DockerRuntimeRequest.model_validate(
            {"image": "x", "command": ["python"], "timeout_seconds": 0}
        )
    with pytest.raises(ValidationError):
        DockerRuntimeRequest.model_validate(
            {"image": "", "command": ["python"], "timeout_seconds": 5}
        )
    with pytest.raises(ValidationError):
        DockerRuntimeRequest.model_validate(
            {
                "image": "x",
                "command": ["python"],
                "timeout_seconds": 5,
                "mounts": [{"source": "", "target": "/workspace"}],
            }
        )


def test_infra_error_envelope_behavior() -> None:
    envelope = ErrorEnvelope.model_validate(
        {
            "code": "timeout",
            "message": "request exceeded timeout",
            "retriable": True,
            "details": {"attempt": 2},
        }
    )
    assert envelope.code == ErrorCode.TIMEOUT
    envelope_dump = envelope.model_dump(mode="json")
    assert (
        ErrorEnvelope.model_validate(envelope_dump).model_dump(mode="json")
        == envelope_dump
    )

    with pytest.raises(ValidationError):
        ErrorEnvelope.model_validate({"code": "unknown", "message": "bad"})
    with pytest.raises(ValidationError):
        ErrorEnvelope.model_validate({"code": "timeout", "message": ""})
    with pytest.raises(ValidationError):
        ErrorEnvelope.model_validate(
            {
                "code": "timeout",
                "message": "bad details",
                "details": {"not_json": object()},
            }
        )
    with pytest.raises(ValidationError):
        ErrorEnvelope.model_validate(
            {
                "code": "timeout",
                "message": "bad details",
                "details": {"not_json": float("nan")},
            }
        )


def test_result_envelopes_reject_success_with_error() -> None:
    with pytest.raises(ValidationError):
        DockerRuntimeResult.model_validate(
            {
                "ok": True,
                "error": {
                    "code": "internal_error",
                    "message": "should not be present on success",
                },
            }
        )

    with pytest.raises(ValidationError):
        DockerRuntimeResult.model_validate(
            {
                "ok": False,
                "exit_code": 1,
            }
        )


def test_removed_error_codes_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ErrorEnvelope.model_validate(
            {"code": "auth", "message": "deprecated code should fail"}
        )

    with pytest.raises(ValidationError):
        ErrorEnvelope.model_validate(
            {"code": "malformed_request", "message": "deprecated code should fail"}
        )


def test_contract_version_is_exposed_and_non_empty() -> None:
    assert isinstance(CONTRACT_VERSION, str)
    assert CONTRACT_VERSION.strip()


def test_contract_version_matches_package_version() -> None:
    assert CONTRACT_VERSION == __version__

    repo_root = Path(__file__).resolve().parent.parent
    pyproject = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    version_match = re.search(
        r'(?m)^version\s*=\s*"(?P<version>[^"]+)"\s*$',
        pyproject,
    )
    assert version_match is not None
    assert version_match.group("version") == __version__


def test_security_profile_defaults() -> None:
    profile = SecurityProfile()
    assert profile.read_only is True
    assert profile.cap_drop == "ALL"
    assert profile.no_new_privileges is True
    assert profile.network_disabled is True


def test_resource_limits_defaults() -> None:
    limits = ResourceLimits()
    assert limits.memory == "256m"
    assert limits.cpus == 0.5
    assert limits.pids_limit == 64
    assert limits.cpu_seconds is None
    assert limits.fsize_bytes is None
    assert limits.nofile is None
    assert limits.nproc is None


def test_tmpfs_mount_defaults() -> None:
    tmpfs = TmpfsMount()
    assert tmpfs.target == "/tmp"
    assert tmpfs.size == "16m"
    assert tmpfs.exec is False


def test_request_with_expanded_fields_roundtrip() -> None:
    req = DockerRuntimeRequest(
        image="alpine:latest",
        command=["echo", "hello"],
        entrypoint="/bin/sh",
        timeout_seconds=10,
        stdin_payload=b"input data",
        security=SecurityProfile(network_disabled=False),
        resources=ResourceLimits(memory="512m", pids_limit=256, fsize_bytes=1024),
        tmpfs=[TmpfsMount(target="/tmp", size="32m", exec=True)],
    )
    assert req.entrypoint == "/bin/sh"
    assert req.stdin_payload == b"input data"
    assert req.security.network_disabled is False
    assert req.resources.memory == "512m"
    assert req.tmpfs[0].exec is True

    dump = req.model_dump(mode="json")
    restored = DockerRuntimeRequest.model_validate(dump)
    assert restored.entrypoint == "/bin/sh"
    assert restored.resources.pids_limit == 256
