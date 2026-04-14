from __future__ import annotations

from dr_docker import (
    DockerRuntimeRequest,
    DockerRuntimeResult,
    ErrorCode,
    ErrorEnvelope,
    RuntimePrimitiveError,
    execute_batch_in_container,
    run_batch_with_failure_isolation,
)


def _runtime_infra_error(message: str) -> RuntimePrimitiveError:
    return RuntimePrimitiveError(
        ErrorEnvelope(
            code=ErrorCode.UNAVAILABLE,
            message=message,
            retriable=True,
        )
    )


class _StubRuntimeAdapter:
    def __init__(self, result: DockerRuntimeResult) -> None:
        self.result = result
        self.requests: list[DockerRuntimeRequest] = []

    def execute_in_runtime(self, request: DockerRuntimeRequest) -> DockerRuntimeResult:
        self.requests.append(request)
        return self.result


def test_execute_batch_in_container_returns_aligned_results() -> None:
    adapter = _StubRuntimeAdapter(
        DockerRuntimeResult(ok=True, exit_code=0, stdout='{"results":[10,20,30]}')
    )
    built_batches: list[list[str]] = []
    parsed_stdout: list[str] = []

    results = execute_batch_in_container(
        ["job-a", "job-b", "job-c"],
        adapter=adapter,
        build_request=lambda items: (
            built_batches.append(items.copy())
            or DockerRuntimeRequest(
                image="generic-worker:latest",
                command=["/app/worker", "run-batch"],
                timeout_seconds=45,
                stdin_payload="batch payload".encode("utf-8"),
            )
        ),
        parse_results=lambda runtime_result: (
            parsed_stdout.append(runtime_result.stdout) or [10, 20, 30]
        ),
    )

    assert results == [10, 20, 30]
    assert built_batches == [["job-a", "job-b", "job-c"]]
    assert parsed_stdout == ['{"results":[10,20,30]}']
    assert len(adapter.requests) == 1
    assert adapter.requests[0].image == "generic-worker:latest"


def test_execute_batch_in_container_rejects_result_count_mismatch() -> None:
    adapter = _StubRuntimeAdapter(DockerRuntimeResult(ok=True, exit_code=0))

    try:
        execute_batch_in_container(
            ["alpha", "beta"],
            adapter=adapter,
            build_request=lambda items: DockerRuntimeRequest(
                image="generic-worker:latest",
                command=["worker"],
                timeout_seconds=len(items) + 1,
            ),
            parse_results=lambda runtime_result: [runtime_result.exit_code],
        )
    except ValueError as exc:
        assert str(exc) == "Batch result count mismatch: expected 2, got 1"
    else:
        raise AssertionError("Expected batch result count mismatch to raise ValueError")


def test_execute_batch_in_container_returns_empty_list_without_running() -> None:
    calls = {"build": 0, "parse": 0}
    adapter = _StubRuntimeAdapter(DockerRuntimeResult(ok=True, exit_code=0))

    results = execute_batch_in_container(
        [],
        adapter=adapter,
        build_request=lambda items: (
            calls.__setitem__("build", calls["build"] + 1)
            or DockerRuntimeRequest(
                image="unused",
                command=["worker"],
                timeout_seconds=max(1, len(items)),
            )
        ),
        parse_results=lambda runtime_result: (
            calls.__setitem__("parse", calls["parse"] + 1) or [runtime_result.stdout]
        ),
    )

    assert results == []
    assert calls == {"build": 0, "parse": 0}
    assert adapter.requests == []


def test_execute_batch_in_container_raises_runtime_primitive_error_on_infra_failure() -> None:
    adapter = _StubRuntimeAdapter(
        DockerRuntimeResult(
            ok=False,
            error=ErrorEnvelope(
                code=ErrorCode.TIMEOUT,
                message="Container timed out after 12s",
                retriable=True,
            ),
        )
    )

    try:
        execute_batch_in_container(
            ["task-1"],
            adapter=adapter,
            build_request=lambda items: DockerRuntimeRequest(
                image="generic-worker:latest",
                command=["worker"],
                timeout_seconds=len(items) * 12,
            ),
            parse_results=lambda runtime_result: [runtime_result.stdout],
        )
    except RuntimePrimitiveError as exc:
        assert exc.error.code is ErrorCode.TIMEOUT
        assert exc.error.message == "Container timed out after 12s"
        assert exc.error.retriable is True
    else:
        raise AssertionError("Expected infra failure to raise RuntimePrimitiveError")


def test_execute_batch_in_container_stays_payload_neutral() -> None:
    adapter = _StubRuntimeAdapter(
        DockerRuntimeResult(
            ok=True,
            exit_code=0,
            stdout='{"results":[{"status":"ok"},{"status":"failed","reason":"bad row"}]}',
        )
    )

    results = execute_batch_in_container(
        [
            {"input_uri": "s3://bucket/a.csv"},
            {"input_uri": "s3://bucket/b.csv"},
        ],
        adapter=adapter,
        build_request=lambda items: DockerRuntimeRequest(
            image="data-worker:stable",
            command=["worker", "transform-batch"],
            timeout_seconds=90,
            stdin_payload=str(items).encode("utf-8"),
        ),
        parse_results=lambda runtime_result: [
            {"status": "ok"},
            {"status": "failed", "reason": "bad row"},
        ],
    )

    assert results == [
        {"status": "ok"},
        {"status": "failed", "reason": "bad row"},
    ]
    assert adapter.requests[0].command == ["worker", "transform-batch"]


def test_run_batch_with_failure_isolation_full_batch_success() -> None:
    calls: list[list[int]] = []

    def run_batch(items: list[int]) -> list[str]:
        calls.append(items)
        return [f"result-{item}" for item in items]

    results, infra_failures = run_batch_with_failure_isolation(
        [("a", 1), ("b", 2), ("c", 3)],
        run_batch,
    )

    assert results == {"a": "result-1", "b": "result-2", "c": "result-3"}
    assert infra_failures == {}
    assert calls == [[1, 2, 3]]


def test_run_batch_with_failure_isolation_isolates_one_infra_failure() -> None:
    failing_items = {3}

    def run_batch(items: list[int]) -> list[int]:
        if any(item in failing_items for item in items):
            raise _runtime_infra_error(f"batch failed for {items}")
        return [item * 10 for item in items]

    results, infra_failures = run_batch_with_failure_isolation(
        [("a", 1), ("b", 2), ("c", 3), ("d", 4)],
        run_batch,
    )

    assert results == {"a": 10, "b": 20, "d": 40}
    assert set(infra_failures) == {"c"}
    assert infra_failures["c"].error.code is ErrorCode.UNAVAILABLE
    assert infra_failures["c"].error.message == "batch failed for [3]"


def test_run_batch_with_failure_isolation_isolates_multiple_infra_failures() -> None:
    class _BatchInfraFailure(Exception):
        pass

    failing_items = {2, 5}

    def run_batch(items: list[int]) -> list[str]:
        if any(item in failing_items for item in items):
            raise _BatchInfraFailure(",".join(str(item) for item in items))
        return [f"ok-{item}" for item in items]

    results, infra_failures = run_batch_with_failure_isolation(
        [("one", 1), ("two", 2), ("three", 3), ("four", 4), ("five", 5)],
        run_batch,
        infra_failure_type=_BatchInfraFailure,
    )

    assert results == {
        "one": "ok-1",
        "three": "ok-3",
        "four": "ok-4",
    }
    assert set(infra_failures) == {"two", "five"}
    assert isinstance(infra_failures["two"], _BatchInfraFailure)
    assert str(infra_failures["two"]) == "2"
    assert str(infra_failures["five"]) == "5"


def test_run_batch_with_failure_isolation_handles_empty_input() -> None:
    calls = 0

    def run_batch(items: list[int]) -> list[int]:
        nonlocal calls
        calls += 1
        return items

    results, infra_failures = run_batch_with_failure_isolation([], run_batch)

    assert results == {}
    assert infra_failures == {}
    assert calls == 0


def test_run_batch_with_failure_isolation_rejects_duplicate_item_ids() -> None:
    def run_batch(items: list[int]) -> list[int]:
        return items

    try:
        run_batch_with_failure_isolation(
            [("dup", 1), ("ok", 2), ("dup", 3), ("dup", 4)],
            run_batch,
        )
    except ValueError as exc:
        assert str(exc) == "Duplicate item IDs are not allowed: 'dup'"
    else:
        raise AssertionError("Expected duplicate item IDs to raise ValueError")


def test_run_batch_with_failure_isolation_preserves_result_id_alignment() -> None:
    def run_batch(items: list[int]) -> list[str]:
        return [f"value-{item}" for item in items]

    results, infra_failures = run_batch_with_failure_isolation(
        [("gamma", 3), ("alpha", 1), ("beta", 2)],
        run_batch,
    )

    assert results == {
        "gamma": "value-3",
        "alpha": "value-1",
        "beta": "value-2",
    }
    assert infra_failures == {}
