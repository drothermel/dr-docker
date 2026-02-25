from pathlib import Path
import re

import pytest
from pydantic import ValidationError

from nl_runtime_primitives import (
    CONTRACT_VERSION,
    DockerMount,
    DockerRuntimeRequest,
    DockerRuntimeResult,
    ErrorCode,
    ErrorEnvelope,
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
    assert DockerRuntimeRequest.model_validate(req_dump).model_dump(mode="json") == req_dump

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

    result = DockerRuntimeResult.model_validate(
        {
            "ok": False,
            "exit_code": 124,
            "stderr": "timed out",
            "duration_seconds": 30.0,
            "error": {
                "code": "timeout",
                "message": "container execution timed out",
                "retriable": True,
            },
        }
    )
    result_dump = result.model_dump(mode="json")
    assert DockerRuntimeResult.model_validate(result_dump).model_dump(mode="json") == result_dump
    with pytest.raises(ValidationError):
        DockerRuntimeResult.model_validate({"ok": True, "duration_seconds": -0.1})


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
    assert ErrorEnvelope.model_validate(envelope_dump).model_dump(mode="json") == envelope_dump

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
