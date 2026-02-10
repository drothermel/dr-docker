import pytest

from nl_runtime_primitives import (
    DockerRuntimeRequest,
    DockerRuntimeResult,
    ErrorCode,
    PromptFetchRequest,
    PromptPayload,
    RuntimePrimitiveError,
    RuntimePrimitivesAdapter,
    StubRuntimePrimitivesAdapter,
    TraceAck,
    TraceEventRequest,
)


def test_stub_adapter_is_runtime_primitives_adapter_protocol() -> None:
    adapter = StubRuntimePrimitivesAdapter()
    assert isinstance(adapter, RuntimePrimitivesAdapter)


def test_stub_defaults_to_unavailable_responses() -> None:
    adapter = StubRuntimePrimitivesAdapter()

    docker_result = adapter.execute_in_runtime(
        DockerRuntimeRequest(
            image="python:3.12-slim",
            command=["python", "-c", "print('ok')"],
            timeout_seconds=5,
        )
    )
    assert docker_result.ok is False
    assert docker_result.error is not None
    assert docker_result.error.code == ErrorCode.UNAVAILABLE

    with pytest.raises(RuntimePrimitiveError) as exc_info:
        adapter.fetch_prompt(PromptFetchRequest(prompt_name="fxn-gen/enc-basic"))
    assert exc_info.value.error.code == ErrorCode.UNAVAILABLE

    trace_ack = adapter.emit_trace(TraceEventRequest(event_name="runtime.test"))
    assert trace_ack.accepted is False
    assert trace_ack.error is not None
    assert trace_ack.error.code == ErrorCode.UNAVAILABLE


def test_stub_can_be_seeded_for_success_paths() -> None:
    expected_docker = DockerRuntimeResult(ok=True, exit_code=0, stdout="ok")
    expected_prompt = PromptPayload(
        prompt_name="fxn-gen/enc-basic",
        system_content="sys",
        task_content="task",
        label="latest",
        version=1,
    )
    expected_trace = TraceAck(accepted=True, trace_id="trace_123")

    adapter = StubRuntimePrimitivesAdapter(
        docker_result=expected_docker,
        prompt_payload=expected_prompt,
        trace_ack=expected_trace,
    )

    docker_result = adapter.execute_in_runtime(
        DockerRuntimeRequest(image="python:3.12-slim", timeout_seconds=5)
    )
    assert docker_result == expected_docker

    prompt = adapter.fetch_prompt(PromptFetchRequest(prompt_name="name"))
    assert prompt == expected_prompt

    trace_ack = adapter.emit_trace(TraceEventRequest(event_name="runtime.test"))
    assert trace_ack == expected_trace

