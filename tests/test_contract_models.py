import pytest
from pydantic import ValidationError

from nl_runtime_primitives import (
    CONTRACT_VERSION,
    DockerMount,
    DockerRuntimeRequest,
    DockerRuntimeResult,
    ErrorCode,
    ErrorEnvelope,
    PromptFetchRequest,
    PromptPayload,
    TraceAck,
    TraceEventRequest,
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


def test_langfuse_request_payload_trace_models() -> None:
    fetch_req = PromptFetchRequest.model_validate(
        {"prompt_name": "summarize", "label": "prod", "version": 1}
    )
    fetch_dump = fetch_req.model_dump(mode="json")
    assert PromptFetchRequest.model_validate(fetch_dump).model_dump(mode="json") == fetch_dump

    payload = PromptPayload.model_validate(
        {
            "prompt_name": "summarize",
            "system_content": "You are concise.",
            "task_content": "Summarize this text.",
            "label": "prod",
            "version": 1,
        }
    )
    payload_dump = payload.model_dump(mode="json")
    assert PromptPayload.model_validate(payload_dump).model_dump(mode="json") == payload_dump

    trace = TraceEventRequest.model_validate(
        {
            "event_name": "docker.run",
            "session_id": "session-123",
            "tags": ["runtime", "docker"],
            "metadata": {"attempt": 1},
        }
    )
    trace_dump = trace.model_dump(mode="json")
    assert TraceEventRequest.model_validate(trace_dump).model_dump(mode="json") == trace_dump

    with pytest.raises(ValidationError):
        PromptFetchRequest.model_validate({})
    with pytest.raises(ValidationError):
        PromptFetchRequest.model_validate({"prompt_name": ""})
    with pytest.raises(ValidationError):
        PromptPayload.model_validate({"prompt_name": "x", "system_content": None})
    nullable_system = PromptPayload.model_validate(
        {"prompt_name": "x", "system_content": None, "task_content": "run this"}
    )
    assert nullable_system.system_content is None
    with pytest.raises(ValidationError):
        TraceEventRequest.model_validate({"event_name": ""})


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
        TraceAck.model_validate(
            {
                "accepted": True,
                "error": {
                    "code": "internal_error",
                    "message": "should not be present on accepted trace",
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

    with pytest.raises(ValidationError):
        TraceAck.model_validate(
            {
                "accepted": False,
            }
        )


def test_contract_version_is_exposed_and_non_empty() -> None:
    assert isinstance(CONTRACT_VERSION, str)
    assert CONTRACT_VERSION.strip()
