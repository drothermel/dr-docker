from dr_docker import (
    DockerRuntimeRequest,
    DockerRuntimeResult,
    ErrorCode,
    ErrorEnvelope,
    RuntimeAdapter,
    RuntimePrimitiveError,
    SubprocessDockerAdapter,
    execute_in_runtime_or_raise,
)


class _RuntimeOnly:
    def execute_in_runtime(self, request: DockerRuntimeRequest) -> DockerRuntimeResult:
        del request
        return DockerRuntimeResult(ok=True, exit_code=0)


class _StubRuntimeAdapter:
    def __init__(self, result: DockerRuntimeResult) -> None:
        self.result = result
        self.requests: list[DockerRuntimeRequest] = []

    def execute_in_runtime(self, request: DockerRuntimeRequest) -> DockerRuntimeResult:
        self.requests.append(request)
        return self.result


def test_runtime_protocol_runtime_checkable() -> None:
    assert isinstance(_RuntimeOnly(), RuntimeAdapter)


def test_subprocess_adapter_satisfies_protocol() -> None:
    adapter = SubprocessDockerAdapter()
    assert isinstance(adapter, RuntimeAdapter)


def test_execute_in_runtime_or_raise_returns_same_success_result() -> None:
    request = DockerRuntimeRequest(
        image="alpine:latest",
        command=["echo", "ok"],
        timeout_seconds=5,
    )
    result = DockerRuntimeResult(ok=True, exit_code=0, stdout="ok")
    adapter = _StubRuntimeAdapter(result)

    returned = execute_in_runtime_or_raise(adapter, request)

    assert returned is result
    assert adapter.requests == [request]


def test_execute_in_runtime_or_raise_raises_runtime_primitive_error() -> None:
    request = DockerRuntimeRequest(
        image="alpine:latest",
        command=["echo", "fail"],
        timeout_seconds=5,
    )
    adapter = _StubRuntimeAdapter(
        DockerRuntimeResult(
            ok=False,
            error=ErrorEnvelope(
                code=ErrorCode.UNAVAILABLE,
                message="docker unavailable",
                retriable=True,
            ),
        )
    )

    try:
        execute_in_runtime_or_raise(adapter, request)
    except RuntimePrimitiveError as exc:
        assert exc.error.code is ErrorCode.UNAVAILABLE
        assert exc.error.message == "docker unavailable"
    else:
        raise AssertionError("Expected RuntimePrimitiveError on infra failure")

    assert adapter.requests == [request]


def test_execute_in_runtime_or_raise_rejects_missing_error_envelope() -> None:
    request = DockerRuntimeRequest(
        image="alpine:latest",
        command=["echo", "bad"],
        timeout_seconds=5,
    )
    invalid_result = DockerRuntimeResult.model_construct(
        ok=False,
        exit_code=None,
        stdout="",
        stderr="",
        duration_seconds=None,
        container_id=None,
        error=None,
    )
    adapter = _StubRuntimeAdapter(invalid_result)

    try:
        execute_in_runtime_or_raise(adapter, request)
    except RuntimePrimitiveError as exc:
        assert exc.error.code is ErrorCode.INTERNAL_ERROR
        assert exc.error.message == (
            "RuntimeAdapter returned ok=False without an error envelope"
        )
        assert exc.error.details == {
            "contract_violation": "ok_false_without_error"
        }
    else:
        raise AssertionError(
            "Expected missing error envelope to raise RuntimePrimitiveError"
        )

    assert adapter.requests == [request]


def test_execute_in_runtime_or_raise_rejects_success_with_error_envelope() -> None:
    request = DockerRuntimeRequest(
        image="alpine:latest",
        command=["echo", "bad"],
        timeout_seconds=5,
    )
    invalid_result = DockerRuntimeResult.model_construct(
        ok=True,
        exit_code=0,
        stdout="ok",
        stderr="",
        duration_seconds=None,
        container_id=None,
        error=ErrorEnvelope(
            code=ErrorCode.INTERNAL_ERROR,
            message="unexpected envelope",
        ),
    )
    adapter = _StubRuntimeAdapter(invalid_result)

    try:
        execute_in_runtime_or_raise(adapter, request)
    except RuntimePrimitiveError as exc:
        assert exc.error.code is ErrorCode.INTERNAL_ERROR
        assert exc.error.message == (
            "RuntimeAdapter returned ok=True with an unexpected error envelope"
        )
        assert exc.error.details == {"contract_violation": "ok_true_with_error"}
    else:
        raise AssertionError(
            "Expected success-with-error envelope to raise RuntimePrimitiveError"
        )

    assert adapter.requests == [request]
